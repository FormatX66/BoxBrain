#include <windows.h>
#include <msctf.h>
#include <objbase.h>

#include <atomic>
#include <string>

#include "friction_detector.h"

namespace {

// {DB122EA1-B433-4BE3-9F97-7F90911E2D66}
constexpr GUID kClsidTypeTrix =
{0xdb122ea1, 0xb433, 0x4be3, {0x9f, 0x97, 0x7f, 0x90, 0x91, 0x1e, 0x2d, 0x66}};

// {763D4E3E-4F4B-40CD-B5DF-B3B1AE6FD4F4}
constexpr GUID kProfileTypeTrix =
{0x763d4e3e, 0x4f4b, 0x40cd, {0xb5, 0xdf, 0xb3, 0xb1, 0xae, 0x6f, 0xd4, 0xf4}};

constexpr wchar_t kServiceName[] = L"TypeTrix Adaptive Typing";
constexpr LANGID kLanguageId = MAKELANGID(LANG_ENGLISH, SUBLANG_ENGLISH_US);

HMODULE g_module = nullptr;
std::atomic<long> g_live_objects{0};

std::wstring GuidString(REFGUID guid) {
    wchar_t buffer[64]{};
    if (StringFromGUID2(guid, buffer, static_cast<int>(std::size(buffer))) <= 0) {
        return {};
    }
    return buffer;
}

std::uint64_t NowMs() {
    return static_cast<std::uint64_t>(GetTickCount64());
}

bool IsNavigationKey(WPARAM key) {
    switch (key) {
        case VK_LEFT:
        case VK_RIGHT:
        case VK_UP:
        case VK_DOWN:
        case VK_HOME:
        case VK_END:
        case VK_PRIOR:
        case VK_NEXT:
            return true;
        default:
            return false;
    }
}

bool IsModifierKey(WPARAM key) {
    switch (key) {
        case VK_SHIFT:
        case VK_LSHIFT:
        case VK_RSHIFT:
        case VK_CONTROL:
        case VK_LCONTROL:
        case VK_RCONTROL:
        case VK_MENU:
        case VK_LMENU:
        case VK_RMENU:
        case VK_LWIN:
        case VK_RWIN:
        case VK_CAPITAL:
        case VK_NUMLOCK:
        case VK_SCROLL:
            return true;
        default:
            return false;
    }
}

class TypeTrixTextService final : public ITfTextInputProcessorEx, public ITfKeyEventSink {
public:
    TypeTrixTextService() { ++g_live_objects; }
    ~TypeTrixTextService() override {
        Deactivate();
        --g_live_objects;
    }

    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID riid, void** object) override {
        if (!object) {
            return E_POINTER;
        }
        *object = nullptr;

        if (riid == IID_IUnknown || riid == IID_ITfTextInputProcessor || riid == IID_ITfTextInputProcessorEx) {
            *object = static_cast<ITfTextInputProcessorEx*>(this);
        } else if (riid == IID_ITfKeyEventSink) {
            *object = static_cast<ITfKeyEventSink*>(this);
        } else {
            return E_NOINTERFACE;
        }

        AddRef();
        return S_OK;
    }

    ULONG STDMETHODCALLTYPE AddRef() override {
        return static_cast<ULONG>(++refs_);
    }

    ULONG STDMETHODCALLTYPE Release() override {
        const ULONG remaining = static_cast<ULONG>(--refs_);
        if (remaining == 0) {
            delete this;
        }
        return remaining;
    }

    HRESULT STDMETHODCALLTYPE Activate(ITfThreadMgr* thread_mgr, TfClientId client_id) override {
        return ActivateEx(thread_mgr, client_id, 0);
    }

    HRESULT STDMETHODCALLTYPE ActivateEx(ITfThreadMgr* thread_mgr, TfClientId client_id, DWORD) override {
        if (!thread_mgr) {
            return E_INVALIDARG;
        }
        if (thread_mgr_) {
            return S_OK;
        }

        thread_mgr_ = thread_mgr;
        thread_mgr_->AddRef();
        client_id_ = client_id;

        ITfKeystrokeMgr* keystroke_mgr = nullptr;
        HRESULT hr = thread_mgr_->QueryInterface(IID_ITfKeystrokeMgr, reinterpret_cast<void**>(&keystroke_mgr));
        if (FAILED(hr)) {
            Deactivate();
            return hr;
        }

        hr = keystroke_mgr->AdviseKeyEventSink(client_id_, this, TRUE);
        keystroke_mgr->Release();
        if (FAILED(hr)) {
            Deactivate();
            return hr;
        }

        key_sink_advised_ = true;
        detector_.reset();
        return S_OK;
    }

    HRESULT STDMETHODCALLTYPE Deactivate() override {
        if (thread_mgr_ && key_sink_advised_) {
            ITfKeystrokeMgr* keystroke_mgr = nullptr;
            if (SUCCEEDED(thread_mgr_->QueryInterface(IID_ITfKeystrokeMgr,
                                                      reinterpret_cast<void**>(&keystroke_mgr)))) {
                keystroke_mgr->UnadviseKeyEventSink(client_id_);
                keystroke_mgr->Release();
            }
        }

        key_sink_advised_ = false;
        client_id_ = TF_CLIENTID_NULL;
        detector_.reset();

        if (thread_mgr_) {
            thread_mgr_->Release();
            thread_mgr_ = nullptr;
        }
        return S_OK;
    }

    HRESULT STDMETHODCALLTYPE OnSetFocus(BOOL) override {
        return S_OK;
    }

    HRESULT STDMETHODCALLTYPE OnTestKeyDown(ITfContext*, WPARAM, LPARAM, BOOL* eaten) override {
        if (!eaten) return E_POINTER;
        *eaten = FALSE;
        return S_OK;
    }

    HRESULT STDMETHODCALLTYPE OnKeyDown(ITfContext*, WPARAM key, LPARAM, BOOL* eaten) override {
        if (!eaten) return E_POINTER;
        *eaten = FALSE; // TypeTrix v0 observes only; it never steals the user's keystroke.

        typetrix::EditEvent event;
        event.timestamp_ms = NowMs();

        if (key == VK_BACK) {
            event.type = typetrix::EventType::Backspace;
        } else if (key == VK_DELETE) {
            event.type = typetrix::EventType::DeleteKey;
        } else if (IsNavigationKey(key)) {
            event.type = typetrix::EventType::Navigation;
        } else if (IsModifierKey(key)) {
            return S_OK;
        } else {
            event.type = typetrix::EventType::Input;
        }

        // v0 deliberately records no raw characters. Later TSF edit-session code can supply
        // short-lived context only after protected/password-context suppression is proven.
        const auto signal = detector_.observe(event);
        if (signal.show_candidates) {
            OutputDebugStringW(L"TypeTrix: probable typing-friction episode detected.\n");
        }
        return S_OK;
    }

    HRESULT STDMETHODCALLTYPE OnTestKeyUp(ITfContext*, WPARAM, LPARAM, BOOL* eaten) override {
        if (!eaten) return E_POINTER;
        *eaten = FALSE;
        return S_OK;
    }

    HRESULT STDMETHODCALLTYPE OnKeyUp(ITfContext*, WPARAM, LPARAM, BOOL* eaten) override {
        if (!eaten) return E_POINTER;
        *eaten = FALSE;
        return S_OK;
    }

    HRESULT STDMETHODCALLTYPE OnPreservedKey(ITfContext*, REFGUID, BOOL* eaten) override {
        if (!eaten) return E_POINTER;
        *eaten = FALSE;
        return S_OK;
    }

private:
    std::atomic<ULONG> refs_{1};
    ITfThreadMgr* thread_mgr_{nullptr};
    TfClientId client_id_{TF_CLIENTID_NULL};
    bool key_sink_advised_{false};
    typetrix::FrictionDetector detector_;
};

class TypeTrixClassFactory final : public IClassFactory {
public:
    TypeTrixClassFactory() { ++g_live_objects; }
    ~TypeTrixClassFactory() override { --g_live_objects; }

    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID riid, void** object) override {
        if (!object) return E_POINTER;
        *object = nullptr;
        if (riid != IID_IUnknown && riid != IID_IClassFactory) {
            return E_NOINTERFACE;
        }
        *object = static_cast<IClassFactory*>(this);
        AddRef();
        return S_OK;
    }

    ULONG STDMETHODCALLTYPE AddRef() override {
        return static_cast<ULONG>(++refs_);
    }

    ULONG STDMETHODCALLTYPE Release() override {
        const ULONG remaining = static_cast<ULONG>(--refs_);
        if (remaining == 0) delete this;
        return remaining;
    }

    HRESULT STDMETHODCALLTYPE CreateInstance(IUnknown* outer, REFIID riid, void** object) override {
        if (!object) return E_POINTER;
        *object = nullptr;
        if (outer) return CLASS_E_NOAGGREGATION;

        auto* service = new (std::nothrow) TypeTrixTextService();
        if (!service) return E_OUTOFMEMORY;
        const HRESULT hr = service->QueryInterface(riid, object);
        service->Release();
        return hr;
    }

    HRESULT STDMETHODCALLTYPE LockServer(BOOL lock) override {
        if (lock) {
            ++g_live_objects;
        } else {
            --g_live_objects;
        }
        return S_OK;
    }

private:
    std::atomic<ULONG> refs_{1};
};

HRESULT RegisterComServer() {
    wchar_t module_path[MAX_PATH]{};
    const DWORD count = GetModuleFileNameW(g_module, module_path, static_cast<DWORD>(std::size(module_path)));
    if (count == 0 || count >= std::size(module_path)) {
        return HRESULT_FROM_WIN32(GetLastError());
    }

    const std::wstring clsid = GuidString(kClsidTypeTrix);
    if (clsid.empty()) return E_FAIL;

    const std::wstring root = L"Software\\Classes\\CLSID\\" + clsid;
    HKEY key = nullptr;
    if (RegCreateKeyExW(HKEY_CURRENT_USER, root.c_str(), 0, nullptr, 0, KEY_WRITE, nullptr, &key, nullptr) != ERROR_SUCCESS) {
        return E_ACCESSDENIED;
    }
    RegSetValueExW(key, nullptr, 0, REG_SZ,
                   reinterpret_cast<const BYTE*>(kServiceName),
                   static_cast<DWORD>((std::size(kServiceName)) * sizeof(wchar_t)));
    RegCloseKey(key);

    const std::wstring inproc = root + L"\\InprocServer32";
    if (RegCreateKeyExW(HKEY_CURRENT_USER, inproc.c_str(), 0, nullptr, 0, KEY_WRITE, nullptr, &key, nullptr) != ERROR_SUCCESS) {
        return E_ACCESSDENIED;
    }

    RegSetValueExW(key, nullptr, 0, REG_SZ,
                   reinterpret_cast<const BYTE*>(module_path),
                   static_cast<DWORD>((wcslen(module_path) + 1) * sizeof(wchar_t)));
    constexpr wchar_t model[] = L"Apartment";
    RegSetValueExW(key, L"ThreadingModel", 0, REG_SZ,
                   reinterpret_cast<const BYTE*>(model),
                   static_cast<DWORD>(sizeof(model)));
    RegCloseKey(key);
    return S_OK;
}

void UnregisterComServer() {
    const std::wstring clsid = GuidString(kClsidTypeTrix);
    if (!clsid.empty()) {
        const std::wstring root = L"Software\\Classes\\CLSID\\" + clsid;
        RegDeleteTreeW(HKEY_CURRENT_USER, root.c_str());
    }
}

HRESULT RegisterTsfProfile() {
    ITfInputProcessorProfiles* profiles = nullptr;
    HRESULT hr = CoCreateInstance(CLSID_TF_InputProcessorProfiles, nullptr, CLSCTX_INPROC_SERVER,
                                  IID_ITfInputProcessorProfiles, reinterpret_cast<void**>(&profiles));
    if (FAILED(hr)) return hr;

    hr = profiles->Register(kClsidTypeTrix);
    if (SUCCEEDED(hr)) {
        wchar_t module_path[MAX_PATH]{};
        const DWORD count = GetModuleFileNameW(g_module, module_path, static_cast<DWORD>(std::size(module_path)));
        if (count == 0 || count >= std::size(module_path)) {
            hr = HRESULT_FROM_WIN32(GetLastError());
        } else {
            hr = profiles->AddLanguageProfile(
                kClsidTypeTrix,
                kLanguageId,
                kProfileTypeTrix,
                kServiceName,
                static_cast<ULONG>(wcslen(kServiceName)),
                module_path,
                count,
                0);
        }
    }
    profiles->Release();
    if (FAILED(hr)) return hr;

    ITfCategoryMgr* categories = nullptr;
    hr = CoCreateInstance(CLSID_TF_CategoryMgr, nullptr, CLSCTX_INPROC_SERVER,
                          IID_ITfCategoryMgr, reinterpret_cast<void**>(&categories));
    if (FAILED(hr)) return hr;

    // Deliberately register only as a keyboard TIP in v0. We do not advertise
    // secure-mode support until protected/password suppression is independently proven.
    hr = categories->RegisterCategory(kClsidTypeTrix, GUID_TFCAT_TIP_KEYBOARD, kClsidTypeTrix);
    categories->Release();
    return hr;
}

void UnregisterTsfProfile() {
    ITfCategoryMgr* categories = nullptr;
    if (SUCCEEDED(CoCreateInstance(CLSID_TF_CategoryMgr, nullptr, CLSCTX_INPROC_SERVER,
                                   IID_ITfCategoryMgr, reinterpret_cast<void**>(&categories)))) {
        categories->UnregisterCategory(kClsidTypeTrix, GUID_TFCAT_TIP_KEYBOARD, kClsidTypeTrix);
        categories->Release();
    }

    ITfInputProcessorProfiles* profiles = nullptr;
    if (SUCCEEDED(CoCreateInstance(CLSID_TF_InputProcessorProfiles, nullptr, CLSCTX_INPROC_SERVER,
                                   IID_ITfInputProcessorProfiles, reinterpret_cast<void**>(&profiles)))) {
        profiles->RemoveLanguageProfile(kClsidTypeTrix, kLanguageId, kProfileTypeTrix);
        profiles->Unregister(kClsidTypeTrix);
        profiles->Release();
    }
}

class ComInit {
public:
    ComInit() {
        hr_ = CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);
        owns_ = SUCCEEDED(hr_);
        if (hr_ == RPC_E_CHANGED_MODE) hr_ = S_OK;
    }
    ~ComInit() {
        if (owns_) CoUninitialize();
    }
    HRESULT result() const { return hr_; }
private:
    HRESULT hr_{E_FAIL};
    bool owns_{false};
};

} // namespace

BOOL APIENTRY DllMain(HMODULE module, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) {
        g_module = module;
        DisableThreadLibraryCalls(module);
    }
    return TRUE;
}

extern "C" HRESULT __stdcall DllCanUnloadNow() {
    return g_live_objects.load() == 0 ? S_OK : S_FALSE;
}

extern "C" HRESULT __stdcall DllGetClassObject(REFCLSID clsid, REFIID riid, void** object) {
    if (!object) return E_POINTER;
    *object = nullptr;
    if (clsid != kClsidTypeTrix) return CLASS_E_CLASSNOTAVAILABLE;

    auto* factory = new (std::nothrow) TypeTrixClassFactory();
    if (!factory) return E_OUTOFMEMORY;
    const HRESULT hr = factory->QueryInterface(riid, object);
    factory->Release();
    return hr;
}

extern "C" HRESULT __stdcall DllRegisterServer() {
    ComInit com;
    if (FAILED(com.result())) return com.result();

    HRESULT hr = RegisterComServer();
    if (FAILED(hr)) return hr;

    hr = RegisterTsfProfile();
    if (FAILED(hr)) {
        UnregisterComServer();
        return hr;
    }
    return S_OK;
}

extern "C" HRESULT __stdcall DllUnregisterServer() {
    ComInit com;
    if (SUCCEEDED(com.result())) {
        UnregisterTsfProfile();
    }
    UnregisterComServer();
    return S_OK;
}
