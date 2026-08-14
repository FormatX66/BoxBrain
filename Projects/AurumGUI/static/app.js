const state = {
  messages: [],
  status: null,
  sending: false,
};

const $ = (id) => document.getElementById(id);

function formatBytes(bytes) {
  if (typeof bytes !== "number" || !Number.isFinite(bytes) || bytes <= 0) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  return `${value >= 10 || index === 0 ? value.toFixed(0) : value.toFixed(1)} ${units[index]}`;
}

function setConnection(ok, label) {
  const dot = $("system-dot");
  dot.className = `dot ${ok ? "good" : "bad"}`;
  $("system-state").textContent = label;
}

function setLLM(llm) {
  const chip = $("llm-chip");
  const available = Boolean(llm && llm.available);
  chip.className = `status-chip ${available ? "good" : "bad"}`;
  chip.textContent = available ? "LLM ready" : "LLM offline";
  $("model-value").textContent = (llm && llm.model) || "aurum-seed";
  $("model-detail").textContent = available ? "local reasoning core ready" : ((llm && llm.state) || "offline");
}

function renderStatus(payload) {
  state.status = payload;
  const machine = payload.machine || {};
  const aurum = payload.aurum || {};
  const llm = payload.llm || {};

  $("host-label").textContent = machine.hostname || "local machine";
  $("arch-pill").textContent = `arch ${machine.architecture || "—"}`;
  $("kernel-pill").textContent = `kernel ${machine.kernel || "—"}`;
  $("cpu-value").textContent = machine.cpu_count ?? "—";
  $("memory-value").textContent = formatBytes(machine.memory_total_bytes);
  $("pci-value").textContent = machine.pci_device_count ?? "—";
  $("usb-value").textContent = machine.usb_device_count ?? "—";
  $("machine-value").textContent = machine.model || "—";
  $("vendor-value").textContent = machine.vendor || "—";
  $("network-value").textContent = (machine.network_interfaces || []).join(", ") || "—";
  $("storage-value").textContent = (machine.block_devices || []).join(", ") || "—";
  $("frontier-value").textContent = aurum.next_gap || aurum.latest_completed_gap || "idle";
  $("native-value").textContent = String((aurum.reusable_native_capabilities || []).length);
  const trusted = aurum.trusted_for_continuation;
  $("trust-value").textContent = trusted === true ? "verified" : trusted === false ? "blocked" : "unknown";
  setLLM(llm);
  setConnection(true, "Aurum online");
}

async function refreshStatus() {
  try {
    const response = await fetch("/api/status", { cache: "no-store" });
    if (!response.ok) throw new Error(`status ${response.status}`);
    renderStatus(await response.json());
  } catch (error) {
    setConnection(false, "interface offline");
    const chip = $("llm-chip");
    chip.className = "status-chip bad";
    chip.textContent = "LLM unknown";
  }
}

function addMessage(role, content, extraClass = "") {
  const wrapper = document.createElement("div");
  wrapper.className = `message ${role} ${extraClass}`.trim();
  const label = document.createElement("div");
  label.className = "message-label";
  label.textContent = role === "user" ? "You" : "Aurum";
  const body = document.createElement("div");
  body.className = "message-body";
  body.textContent = content;
  wrapper.append(label, body);
  $("conversation").appendChild(wrapper);
  $("conversation").scrollTop = $("conversation").scrollHeight;
  return wrapper;
}

function setSending(value) {
  state.sending = value;
  $("send").disabled = value;
  $("send").textContent = value ? "Thinking…" : "Send";
}

async function sendPrompt(text) {
  const clean = text.trim();
  if (!clean || state.sending) return;

  addMessage("user", clean);
  state.messages.push({ role: "user", content: clean });
  $("prompt").value = "";
  setSending(true);

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: state.messages }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || payload.error || `chat ${response.status}`);
    const content = payload.content || payload.reasoning_content || "Aurum returned an empty response.";
    addMessage("aurum", content);
    state.messages.push({ role: "assistant", content });
    if (state.messages.length > 24) state.messages = state.messages.slice(-24);
  } catch (error) {
    addMessage("aurum", `Reasoning core unavailable: ${error.message}`, "error");
  } finally {
    setSending(false);
    refreshStatus();
  }
}

function wireNavigation() {
  document.querySelectorAll(".nav-item").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".nav-item").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      const label = button.textContent.trim();
      $("view-title").textContent = label;
      const lens = button.dataset.lens;
      if (lens && lens !== "overview") {
        const hints = {
          kernel: "Kernel lens selected. Ask Aurum about current kernel state, machine contract, or the adaptive Kernel Seed.",
          devices: "Device lens selected. Ask Aurum about attached peripherals and materialized device capabilities.",
          memory: "Memory lens selected. Ask Aurum about durable state, semantic memory, or current machine memory.",
          builds: "Build lens selected. Ask Aurum about OS, kernel, LLM, or GUI build state.",
        };
        $("prompt").placeholder = hints[lens] || "Ask Aurum anything…";
      } else {
        $("prompt").placeholder = "Ask Aurum anything…";
      }
    });
  });
}

$("composer").addEventListener("submit", (event) => {
  event.preventDefault();
  sendPrompt($("prompt").value);
});

$("prompt").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendPrompt($("prompt").value);
  }
});

$("refresh").addEventListener("click", refreshStatus);
wireNavigation();
refreshStatus();
setInterval(refreshStatus, 5000);
