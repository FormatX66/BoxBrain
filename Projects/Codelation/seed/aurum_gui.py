#!/usr/bin/env python3
"""Loopback-only, dialogue-only graphical interface for Aurum on BBPI4.

The browser surface is deliberately dependency-free and inherits the same
bounded dialogue supervisor as ``aurum_console``.  It has no shell, tools, or
host-actuation endpoint.  An API key is accepted only in a request body and is
never written by this module.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from aurum_console import CONSOLE_SCHEMA, DEFAULT_ROOT, console_status
from aurum_dialogue import DEFAULT_MODEL, Reasoner, ask, call_openai_reasoner


GUI_SCHEMA = "aurum.gui.v1"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
MAX_REQUEST_BYTES = 16_384
MAX_API_KEY_CHARS = 512
MAX_MODEL_CHARS = 128
MODEL_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "[::1]", "::1"})

HUMAN_CONSTANTS = (
    "home",
    "back",
    "search",
    "settings",
    "notifications",
    "workspace-switcher",
    "accessibility",
    "session-power",
    "recovery-safe-layout",
    "adaptation-lock",
)

PAGE = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="dark">
  <meta name="aurum-csrf" content="{{CSRF}}">
  <title>Aurum — BBPI4</title>
  <style nonce="{{NONCE}}">
    :root {
      --bg: #080a0f;
      --panel: rgba(17, 20, 29, .88);
      --panel-strong: #11151e;
      --line: rgba(255, 214, 122, .16);
      --line-bright: rgba(255, 214, 122, .40);
      --gold: #f5c451;
      --gold-soft: #ffe6a0;
      --ink: #f6f2e8;
      --muted: #9ea5b5;
      --good: #79dca7;
      --danger: #ff8c8c;
      --shadow: 0 24px 70px rgba(0, 0, 0, .44);
    }
    * { box-sizing: border-box; }
    html, body { min-height: 100%; }
    body {
      margin: 0;
      color: var(--ink);
      background:
        radial-gradient(circle at 72% -8%, rgba(245,196,81,.13), transparent 32rem),
        radial-gradient(circle at 8% 92%, rgba(74,91,138,.16), transparent 34rem),
        var(--bg);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
      overflow-x: hidden;
    }
    button, input, textarea { font: inherit; }
    button { color: inherit; }
    .shell {
      display: grid;
      grid-template-columns: 88px minmax(0, 1fr) 310px;
      min-height: 100vh;
    }
    .rail {
      position: sticky;
      top: 0;
      height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 10px;
      padding: 18px 12px;
      background: rgba(9, 11, 17, .86);
      border-right: 1px solid var(--line);
      backdrop-filter: blur(20px);
      z-index: 3;
    }
    .mark {
      width: 52px;
      height: 52px;
      border-radius: 18px;
      display: grid;
      place-items: center;
      margin-bottom: 18px;
      color: #171106;
      font-weight: 900;
      font-size: 22px;
      background: radial-gradient(circle at 35% 30%, #fff6c6, var(--gold) 52%, #a96814);
      box-shadow: 0 0 34px rgba(245,196,81,.26), inset 0 1px 1px rgba(255,255,255,.7);
    }
    .nav {
      width: 60px;
      min-height: 54px;
      border: 1px solid transparent;
      border-radius: 16px;
      background: transparent;
      color: var(--muted);
      cursor: pointer;
      display: grid;
      place-items: center;
      gap: 2px;
      padding: 7px 4px;
      transition: .18s ease;
    }
    .nav span:first-child { font-size: 18px; line-height: 1; }
    .nav span:last-child { font-size: 9px; letter-spacing: .03em; }
    .nav:hover, .nav.active {
      color: var(--gold-soft);
      border-color: var(--line-bright);
      background: rgba(245,196,81,.08);
      transform: translateY(-1px);
    }
    .nav.safe { margin-top: auto; }
    main {
      min-width: 0;
      padding: 32px clamp(22px, 4vw, 62px) 28px;
      display: flex;
      flex-direction: column;
    }
    .topline { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; }
    .eyebrow { color: var(--gold); font-size: 11px; letter-spacing: .20em; text-transform: uppercase; }
    h1 { margin: 8px 0 4px; font-size: clamp(34px, 5vw, 62px); letter-spacing: -.055em; font-weight: 760; }
    .subtitle { margin: 0; color: var(--muted); max-width: 650px; line-height: 1.55; }
    .online {
      flex: 0 0 auto;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 12px;
      border: 1px solid rgba(121,220,167,.25);
      border-radius: 999px;
      color: var(--good);
      background: rgba(121,220,167,.07);
      font-size: 12px;
    }
    .online::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: currentColor; box-shadow: 0 0 14px currentColor; }
    .chat {
      flex: 1;
      min-height: 420px;
      margin: 42px 0 20px;
      display: flex;
      flex-direction: column;
      gap: 18px;
    }
    .welcome {
      max-width: 720px;
      padding: 24px 26px;
      border: 1px solid var(--line);
      border-radius: 24px 24px 24px 8px;
      background: linear-gradient(145deg, rgba(245,196,81,.08), rgba(20,24,35,.74));
      box-shadow: var(--shadow);
      line-height: 1.62;
    }
    .welcome strong { color: var(--gold-soft); }
    .message { max-width: min(780px, 90%); padding: 16px 19px; border-radius: 20px; white-space: pre-wrap; line-height: 1.55; }
    .message.user { align-self: flex-end; background: #202736; border: 1px solid rgba(255,255,255,.08); border-radius: 20px 20px 7px 20px; }
    .message.aurum { align-self: flex-start; background: rgba(245,196,81,.07); border: 1px solid var(--line); border-radius: 20px 20px 20px 7px; }
    .message.error { align-self: flex-start; color: #ffd1d1; background: rgba(255,90,90,.08); border: 1px solid rgba(255,90,90,.2); }
    .composer {
      position: sticky;
      bottom: 0;
      padding: 15px;
      border: 1px solid var(--line-bright);
      border-radius: 24px;
      background: rgba(15, 18, 26, .94);
      box-shadow: var(--shadow);
      backdrop-filter: blur(22px);
    }
    textarea {
      width: 100%;
      min-height: 62px;
      max-height: 180px;
      resize: vertical;
      border: 0;
      outline: 0;
      padding: 6px 8px 12px;
      color: var(--ink);
      background: transparent;
    }
    textarea::placeholder, input::placeholder { color: #777f8f; }
    .compose-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
    .key-field {
      flex: 1;
      min-width: 140px;
      max-width: 360px;
      padding: 10px 12px;
      border-radius: 13px;
      border: 1px solid rgba(255,255,255,.10);
      outline: none;
      color: var(--ink);
      background: rgba(0,0,0,.18);
    }
    .key-field:focus { border-color: var(--line-bright); }
    .send {
      border: 0;
      border-radius: 14px;
      padding: 11px 18px;
      color: #1a1306;
      background: linear-gradient(135deg, #ffe397, var(--gold));
      font-weight: 800;
      cursor: pointer;
      box-shadow: 0 8px 24px rgba(245,196,81,.18);
    }
    .send:disabled { opacity: .5; cursor: wait; }
    .privacy { margin: 9px 6px 0; color: #7f8797; font-size: 10px; }
    aside {
      position: sticky;
      top: 0;
      height: 100vh;
      padding: 24px 20px;
      border-left: 1px solid var(--line);
      background: rgba(10, 12, 18, .76);
      overflow-y: auto;
      backdrop-filter: blur(18px);
    }
    .aside-title { margin: 6px 0 18px; font-size: 13px; letter-spacing: .12em; text-transform: uppercase; color: var(--gold-soft); }
    .card { margin-bottom: 14px; padding: 16px; border: 1px solid var(--line); border-radius: 18px; background: var(--panel); }
    .card h2 { margin: 0 0 13px; font-size: 12px; color: var(--muted); font-weight: 650; text-transform: uppercase; letter-spacing: .09em; }
    .metric { display: flex; justify-content: space-between; gap: 10px; margin: 9px 0; font-size: 12px; }
    .metric span:first-child { color: var(--muted); }
    .metric span:last-child { text-align: right; overflow-wrap: anywhere; }
    .boundary { display: flex; align-items: center; gap: 8px; margin: 9px 0; font-size: 12px; color: var(--good); }
    .boundary::before { content: "✓"; width: 18px; height: 18px; display: grid; place-items: center; border-radius: 50%; background: rgba(121,220,167,.10); }
    .proof-button { width: 100%; padding: 10px; border: 1px solid var(--line-bright); border-radius: 12px; color: var(--gold-soft); background: rgba(245,196,81,.06); cursor: pointer; }
    .hidden { display: none !important; }
    .safe-banner { margin: 28px 0 0; padding: 14px 16px; border: 1px solid rgba(121,220,167,.22); border-radius: 15px; color: var(--good); background: rgba(121,220,167,.06); }
    @media (max-width: 980px) {
      .shell { grid-template-columns: 72px minmax(0, 1fr); }
      aside { grid-column: 2; position: static; height: auto; border-left: 0; border-top: 1px solid var(--line); }
      .rail { width: 72px; }
    }
    @media (max-width: 640px) {
      .shell { display: block; }
      .rail { position: sticky; width: 100%; height: auto; flex-direction: row; padding: 8px; overflow-x: auto; border-right: 0; border-bottom: 1px solid var(--line); }
      .mark { width: 42px; height: 42px; margin: 0 8px 0 0; flex: 0 0 auto; }
      .nav { min-width: 52px; min-height: 46px; }
      .nav.safe { margin: 0 0 0 auto; }
      main { padding: 24px 16px; }
      aside { padding: 20px 16px 32px; }
      .topline { display: block; }
      .online { margin-top: 18px; }
      .chat { min-height: 340px; margin-top: 30px; }
      .compose-row { align-items: stretch; flex-direction: column; }
      .key-field { max-width: none; }
    }
  </style>
</head>
<body>
<div class="shell">
  <nav class="rail" aria-label="Aurum landmarks">
    <div class="mark" aria-label="Aurum">A</div>
    <button class="nav active" data-action="home"><span>⌂</span><span>Home</span></button>
    <button class="nav" data-action="back"><span>←</span><span>Back</span></button>
    <button class="nav" data-action="search"><span>⌕</span><span>Search</span></button>
    <button class="nav" data-action="workspaces"><span>▦</span><span>Spaces</span></button>
    <button class="nav" data-action="notices"><span>◌</span><span>Notices</span></button>
    <button class="nav" data-action="settings"><span>⚙</span><span>Settings</span></button>
    <button class="nav safe" data-action="safe"><span>◇</span><span>Safe</span></button>
  </nav>

  <main>
    <header class="topline">
      <div>
        <div class="eyebrow">BBPI4 · Local adaptive shell</div>
        <h1>Good to see you.</h1>
        <p class="subtitle">Aurum is present through a bounded conversational surface. You decide what changes; the familiar way back stays visible.</p>
      </div>
      <div id="online" class="online">Connecting</div>
    </header>

    <div id="safeBanner" class="safe-banner hidden">Safe Layout is active. Adaptive emphasis is paused and all human landmarks remain available.</div>

    <section id="chat" class="chat" aria-live="polite">
      <div class="welcome"><strong>Aurum is ready.</strong><br>This first GUI keeps dialogue separate from machine authority. Ask a question, inspect Proof View, or choose Safe Layout at any time.</div>
    </section>

    <form id="composer" class="composer">
      <textarea id="prompt" maxlength="12000" aria-label="Message Aurum" placeholder="Talk with Aurum…" required></textarea>
      <div class="compose-row">
        <input id="apiKey" class="key-field" type="password" maxlength="512" autocomplete="off" spellcheck="false" aria-label="OpenAI API key" placeholder="OpenAI API key · memory only">
        <button id="send" class="send" type="submit">Send to Aurum</button>
      </div>
      <p class="privacy">The key stays only in this open page and request memory. Aurum receives no shell or host-control capability.</p>
    </form>
  </main>

  <aside id="proof">
    <div class="aside-title">Proof View</div>
    <div class="card">
      <h2>Identity</h2>
      <div class="metric"><span>Node</span><span id="identity">—</span></div>
      <div class="metric"><span>Mind</span><span id="mind">—</span></div>
      <div class="metric"><span>Model</span><span id="model">—</span></div>
    </div>
    <div class="card">
      <h2>Safety boundary</h2>
      <div class="boundary">Dialogue only</div>
      <div class="boundary">Host actuation off</div>
      <div class="boundary">API key not persisted</div>
      <div class="boundary">Loopback + SSH tunnel</div>
      <div class="boundary">Safe Layout available</div>
    </div>
    <div class="card">
      <h2>Adaptation</h2>
      <div class="metric"><span>Mode</span><span id="mode">General</span></div>
      <div class="metric"><span>Lock</span><span id="lock">User controlled</span></div>
      <div class="metric"><span>Evidence</span><span id="evidenceCount">0 records</span></div>
      <button id="refreshProof" class="proof-button" type="button">Refresh proof</button>
    </div>
  </aside>
</div>
<script nonce="{{NONCE}}">
  const csrf = document.querySelector('meta[name="aurum-csrf"]').content;
  const chat = document.getElementById('chat');
  const prompt = document.getElementById('prompt');
  const apiKey = document.getElementById('apiKey');
  const send = document.getElementById('send');
  let safeLayout = false;

  function addMessage(kind, text) {
    const node = document.createElement('div');
    node.className = `message ${kind}`;
    node.textContent = text;
    chat.appendChild(node);
    node.scrollIntoView({behavior: 'smooth', block: 'end'});
  }

  async function refreshStatus() {
    try {
      const response = await fetch('/api/status', {cache: 'no-store'});
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Status unavailable');
      document.getElementById('online').textContent = 'Pi connected';
      document.getElementById('identity').textContent = data.console.identity;
      document.getElementById('mind').textContent = `v${data.console.mind_version}`;
      document.getElementById('model').textContent = data.console.model;
      document.getElementById('evidenceCount').textContent = `${data.proof_view.dialogue_evidence_count} records`;
    } catch (_) {
      document.getElementById('online').textContent = 'Pi unavailable';
    }
  }

  document.getElementById('composer').addEventListener('submit', async (event) => {
    event.preventDefault();
    const text = prompt.value.trim();
    const key = apiKey.value.trim();
    if (!text) return;
    if (!key) {
      addMessage('error', 'Enter an OpenAI API key. It is used for this request and is not saved by Aurum.');
      apiKey.focus();
      return;
    }
    addMessage('user', text);
    prompt.value = '';
    send.disabled = true;
    send.textContent = 'Thinking…';
    try {
      const response = await fetch('/api/ask', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-Aurum-CSRF': csrf},
        body: JSON.stringify({prompt: text, api_key: key})
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Aurum dialogue unavailable');
      addMessage('aurum', data.response);
      await refreshStatus();
    } catch (error) {
      addMessage('error', error.message || 'Aurum dialogue unavailable');
    } finally {
      send.disabled = false;
      send.textContent = 'Send to Aurum';
      prompt.focus();
    }
  });

  document.querySelectorAll('.nav').forEach((button) => {
    button.addEventListener('click', () => {
      document.querySelectorAll('.nav').forEach((item) => item.classList.remove('active'));
      button.classList.add('active');
      const action = button.dataset.action;
      if (action === 'safe') {
        safeLayout = true;
        document.getElementById('safeBanner').classList.remove('hidden');
        document.getElementById('mode').textContent = 'Safe / General';
        document.getElementById('lock').textContent = 'Adaptation paused';
      } else if (action === 'home') {
        window.scrollTo({top: 0, behavior: 'smooth'});
        prompt.focus();
      } else if (action === 'back') {
        history.back();
      } else if (action === 'settings') {
        apiKey.focus();
      } else {
        addMessage('aurum', `${button.querySelector('span:last-child').textContent} remains a stable landmark. This bounded first GUI does not actuate that host feature.`);
      }
    });
  });

  document.getElementById('refreshProof').addEventListener('click', refreshStatus);
  prompt.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      document.getElementById('composer').requestSubmit();
    }
  });
  refreshStatus();
</script>
</body>
</html>
"""


class AurumGuiServer(ThreadingHTTPServer):
    """HTTP server carrying only the bounded Aurum GUI configuration."""

    daemon_threads = True
    allow_reuse_address = False

    def __init__(
        self,
        server_address: tuple[str, int],
        root: Path,
        model: str,
        reasoner: Reasoner,
    ) -> None:
        super().__init__(server_address, AurumGuiHandler)
        self.aurum_root = root.expanduser().resolve()
        self.aurum_model = model
        self.aurum_reasoner = reasoner
        self.csrf_token = secrets.token_urlsafe(32)


class AurumGuiHandler(BaseHTTPRequestHandler):
    """Serve the static shell and a two-endpoint dialogue API."""

    server: AurumGuiServer

    def log_message(self, format: str, *args: object) -> None:
        # Avoid request-path and dialogue-related logs. Lifecycle logging happens
        # in main and contains no user content.
        return

    def _security_headers(self, *, nonce: str | None = None) -> None:
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=(), payment=(), usb=(), serial=()",
        )
        if nonce is not None:
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; "
                f"style-src 'nonce-{nonce}'; script-src 'nonce-{nonce}'; "
                "connect-src 'self'; img-src 'self' data:; "
                "form-action 'self'; base-uri 'none'; frame-ancestors 'none'",
            )

    def _host_is_loopback(self) -> bool:
        raw = self.headers.get("Host", "")
        try:
            parsed = urlsplit(f"//{raw}")
        except ValueError:
            return False
        return parsed.hostname in {"127.0.0.1", "localhost", "::1"}

    def _origin_is_loopback(self) -> bool:
        raw = self.headers.get("Origin", "")
        if not raw:
            return False
        try:
            parsed = urlsplit(raw)
        except ValueError:
            return False
        return parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}

    def _json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._security_headers()
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: HTTPStatus, message: str) -> None:
        self._json(status, {"schema": GUI_SCHEMA, "error": message})

    def _status_payload(self) -> dict[str, Any]:
        current = console_status(self.server.aurum_root, self.server.aurum_model)
        evidence_dir = self.server.aurum_root / "verification" / "dialogue"
        try:
            evidence_count = sum(
                1
                for path in evidence_dir.iterdir()
                if path.is_file() and path.name.startswith("AURUM_ASK_") and path.suffix == ".json"
            )
        except FileNotFoundError:
            evidence_count = 0
        return {
            "schema": GUI_SCHEMA,
            "console_schema": CONSOLE_SCHEMA,
            "console": current,
            "interface": {
                "mode": "general",
                "human_constants": list(HUMAN_CONSTANTS),
                "safe_layout_available": True,
                "adaptation_lock_available": True,
            },
            "proof_view": {
                "present": True,
                "dialogue_evidence_count": evidence_count,
                "user_content_returned": False,
            },
            "transport": {
                "loopback_only": True,
                "ssh_tunnel_required": True,
            },
            "authority": {
                "dialogue_only": True,
                "host_actuation": False,
                "api_key_persisted": False,
            },
        }

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        if not self._host_is_loopback():
            self._error(HTTPStatus.BAD_REQUEST, "loopback host required")
            return
        path = urlsplit(self.path).path
        if path == "/":
            nonce = secrets.token_urlsafe(18)
            body = (
                PAGE.replace("{{NONCE}}", nonce)
                .replace("{{CSRF}}", self.server.csrf_token)
                .encode("utf-8")
            )
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self._security_headers(nonce=nonce)
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/api/status":
            try:
                self._json(HTTPStatus.OK, self._status_payload())
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                self._error(HTTPStatus.SERVICE_UNAVAILABLE, f"status unavailable: {type(exc).__name__}")
            return
        self._error(HTTPStatus.NOT_FOUND, "not found")

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        if not self._host_is_loopback() or not self._origin_is_loopback():
            self._error(HTTPStatus.FORBIDDEN, "loopback origin required")
            return
        if not secrets.compare_digest(
            self.headers.get("X-Aurum-CSRF", ""), self.server.csrf_token
        ):
            self._error(HTTPStatus.FORBIDDEN, "request proof invalid")
            return
        if urlsplit(self.path).path != "/api/ask":
            self._error(HTTPStatus.NOT_FOUND, "not found")
            return
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            self._error(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "application/json required")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if not 1 <= length <= MAX_REQUEST_BYTES:
            self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "request size invalid")
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._error(HTTPStatus.BAD_REQUEST, "invalid JSON")
            return
        if not isinstance(payload, dict) or not set(payload).issubset({"prompt", "api_key", "model"}):
            self._error(HTTPStatus.BAD_REQUEST, "request fields invalid")
            return
        prompt = payload.get("prompt")
        api_key = payload.get("api_key")
        model = payload.get("model", self.server.aurum_model)
        if not isinstance(prompt, str) or not prompt.strip():
            self._error(HTTPStatus.BAD_REQUEST, "prompt is empty")
            return
        if not isinstance(api_key, str) or not api_key.strip() or len(api_key) > MAX_API_KEY_CHARS:
            self._error(HTTPStatus.BAD_REQUEST, "API key is required")
            return
        if (
            not isinstance(model, str)
            or len(model) > MAX_MODEL_CHARS
            or MODEL_PATTERN.fullmatch(model) is None
        ):
            self._error(HTTPStatus.BAD_REQUEST, "model is invalid")
            return
        try:
            response, evidence = ask(
                self.server.aurum_root,
                prompt=prompt,
                model=model,
                api_key=api_key.strip(),
                reasoner=self.server.aurum_reasoner,
            )
        except Exception as exc:  # keep the GUI available after bounded provider errors
            self._error(
                HTTPStatus.BAD_GATEWAY,
                f"Aurum dialogue unavailable: {type(exc).__name__}",
            )
            return
        self._json(
            HTTPStatus.OK,
            {
                "schema": GUI_SCHEMA,
                "response": response,
                "evidence": evidence.name,
                "host_actuation": False,
                "api_key_persisted": False,
            },
        )


def create_server(
    host: str,
    port: int,
    root: Path,
    model: str = DEFAULT_MODEL,
    reasoner: Reasoner = call_openai_reasoner,
) -> AurumGuiServer:
    if host not in {"127.0.0.1", "::1"}:
        raise ValueError("Aurum GUI must bind to loopback")
    if port != 0 and not 1024 <= port <= 65535:
        raise ValueError("Aurum GUI port must be zero or between 1024 and 65535")
    if len(model) > MAX_MODEL_CHARS or MODEL_PATTERN.fullmatch(model) is None:
        raise ValueError("Aurum model name is invalid")
    return AurumGuiServer((host, port), root, model, reasoner)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="BBPI4 Aurum loopback GUI")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--model", default=os.environ.get("AURUM_MODEL", DEFAULT_MODEL))
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--status", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.status:
        payload = console_status(args.root, args.model)
        payload.update(
            {
                "gui_schema": GUI_SCHEMA,
                "host": args.host,
                "port": args.port,
                "loopback_only": args.host in {"127.0.0.1", "::1"},
                "safe_layout_available": True,
                "proof_view_present": True,
            }
        )
        print(json.dumps(payload, sort_keys=True))
        return 0
    server = create_server(args.host, args.port, args.root, args.model)
    print(
        f"AURUM_GUI_READY address={args.host} port={server.server_address[1]} "
        "dialogue_only=true host_actuation=false",
        flush=True,
    )
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
