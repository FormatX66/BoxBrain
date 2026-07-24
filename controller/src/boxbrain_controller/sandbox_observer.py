from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from dataclasses import dataclass
from io import BytesIO

from PIL import Image


class SandboxCaptureError(RuntimeError):
    """Raised when the Windows Sandbox frame cannot be captured."""


@dataclass(frozen=True, slots=True)
class SandboxWindow:
    handle: int
    title: str
    width: int
    height: int


class _Rect(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class _BitmapInfoHeader(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class _BitmapInfo(ctypes.Structure):
    _fields_ = [
        ("bmiHeader", _BitmapInfoHeader),
        ("bmiColors", wintypes.DWORD * 3),
    ]


class WindowsSandboxObserver:
    """Read-only discovery and frame capture for Windows Sandbox.

    This class intentionally exposes no keyboard, mouse, clipboard, process,
    filesystem, or shell operations.
    """

    target_id = "windows-sandbox"
    target_name = "Windows Sandbox"
    window_title = "Windows Sandbox"

    def __init__(self, *, max_frame_width: int = 1600) -> None:
        self._max_frame_width = max_frame_width
        self._supported = sys.platform == "win32"
        if self._supported:
            self._configure_win32()

    def describe(self) -> dict[str, object]:
        window = self.find_window()
        return {
            "id": self.target_id,
            "name": self.target_name,
            "transport": "local-window-capture",
            "mode": "read-only",
            "connected": window is not None,
            "window_title": window.title if window else self.window_title,
            "frame_endpoint": (
                f"/api/v1/targets/{self.target_id}/frame"
                if window
                else None
            ),
            "input_enabled": False,
        }

    def find_window(self) -> SandboxWindow | None:
        if not self._supported:
            return None

        matches: list[int] = []

        @self._enum_windows_proc
        def visit_window(hwnd: int, _lparam: int) -> bool:
            if not self._user32.IsWindowVisible(hwnd):
                return True
            length = self._user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            buffer = ctypes.create_unicode_buffer(length + 1)
            self._user32.GetWindowTextW(hwnd, buffer, length + 1)
            if buffer.value == self.window_title:
                matches.append(hwnd)
            return True

        self._user32.EnumWindows(visit_window, 0)
        if not matches:
            return None

        rect = _Rect()
        handle = matches[0]
        if not self._user32.GetWindowRect(handle, ctypes.byref(rect)):
            return None
        width = rect.right - rect.left
        height = rect.bottom - rect.top
        if width <= 0 or height <= 0:
            return None
        return SandboxWindow(handle, self.window_title, width, height)

    def capture_png(self) -> bytes:
        window = self.find_window()
        if window is None:
            raise SandboxCaptureError("Windows Sandbox is not running.")

        window_dc = self._user32.GetWindowDC(window.handle)
        if not window_dc:
            raise SandboxCaptureError("Could not access the sandbox window.")

        memory_dc = self._gdi32.CreateCompatibleDC(window_dc)
        bitmap = self._gdi32.CreateCompatibleBitmap(
            window_dc,
            window.width,
            window.height,
        )
        previous = self._gdi32.SelectObject(memory_dc, bitmap)

        try:
            if not self._user32.PrintWindow(window.handle, memory_dc, 2):
                raise SandboxCaptureError("Windows refused the frame capture.")

            info = _BitmapInfo()
            info.bmiHeader.biSize = ctypes.sizeof(_BitmapInfoHeader)
            info.bmiHeader.biWidth = window.width
            info.bmiHeader.biHeight = -window.height
            info.bmiHeader.biPlanes = 1
            info.bmiHeader.biBitCount = 32
            info.bmiHeader.biCompression = 0
            pixels = ctypes.create_string_buffer(
                window.width * window.height * 4
            )
            copied_lines = self._gdi32.GetDIBits(
                memory_dc,
                bitmap,
                0,
                window.height,
                pixels,
                ctypes.byref(info),
                0,
            )
            if copied_lines != window.height:
                raise SandboxCaptureError("The sandbox frame was incomplete.")

            image = Image.frombuffer(
                "RGB",
                (window.width, window.height),
                pixels,
                "raw",
                "BGRX",
                0,
                1,
            ).copy()
            if image.width > self._max_frame_width:
                height = round(
                    image.height * self._max_frame_width / image.width
                )
                image = image.resize(
                    (self._max_frame_width, height),
                    Image.Resampling.LANCZOS,
                )
            output = BytesIO()
            image.save(output, format="PNG", optimize=True)
            return output.getvalue()
        finally:
            if previous:
                self._gdi32.SelectObject(memory_dc, previous)
            if bitmap:
                self._gdi32.DeleteObject(bitmap)
            if memory_dc:
                self._gdi32.DeleteDC(memory_dc)
            self._user32.ReleaseDC(window.handle, window_dc)

    def _configure_win32(self) -> None:
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
        self._enum_windows_proc = ctypes.WINFUNCTYPE(
            wintypes.BOOL,
            wintypes.HWND,
            wintypes.LPARAM,
        )

        self._user32.EnumWindows.argtypes = [
            self._enum_windows_proc,
            wintypes.LPARAM,
        ]
        self._user32.EnumWindows.restype = wintypes.BOOL
        self._user32.IsWindowVisible.argtypes = [wintypes.HWND]
        self._user32.IsWindowVisible.restype = wintypes.BOOL
        self._user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        self._user32.GetWindowTextLengthW.restype = ctypes.c_int
        self._user32.GetWindowTextW.argtypes = [
            wintypes.HWND,
            wintypes.LPWSTR,
            ctypes.c_int,
        ]
        self._user32.GetWindowTextW.restype = ctypes.c_int
        self._user32.GetWindowRect.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(_Rect),
        ]
        self._user32.GetWindowRect.restype = wintypes.BOOL
        self._user32.GetWindowDC.argtypes = [wintypes.HWND]
        self._user32.GetWindowDC.restype = wintypes.HDC
        self._user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
        self._user32.ReleaseDC.restype = ctypes.c_int
        self._user32.PrintWindow.argtypes = [
            wintypes.HWND,
            wintypes.HDC,
            wintypes.UINT,
        ]
        self._user32.PrintWindow.restype = wintypes.BOOL

        self._gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
        self._gdi32.CreateCompatibleDC.restype = wintypes.HDC
        self._gdi32.CreateCompatibleBitmap.argtypes = [
            wintypes.HDC,
            ctypes.c_int,
            ctypes.c_int,
        ]
        self._gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
        self._gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
        self._gdi32.SelectObject.restype = wintypes.HGDIOBJ
        self._gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
        self._gdi32.DeleteObject.restype = wintypes.BOOL
        self._gdi32.DeleteDC.argtypes = [wintypes.HDC]
        self._gdi32.DeleteDC.restype = wintypes.BOOL
        self._gdi32.GetDIBits.argtypes = [
            wintypes.HDC,
            wintypes.HBITMAP,
            wintypes.UINT,
            wintypes.UINT,
            wintypes.LPVOID,
            ctypes.POINTER(_BitmapInfo),
            wintypes.UINT,
        ]
        self._gdi32.GetDIBits.restype = ctypes.c_int
