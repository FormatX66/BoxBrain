(() => {
  "use strict";

  const STORAGE_KEY = "aurum.ui.interaction.v0";
  const MAX_RECENT = 24;
  const MAX_PROMPTS = 40;

  const defaults = () => ({
    clicks: {},
    transitions: {},
    recent: [],
    prompts: [],
    acceptedSuggestions: 0,
    voiceUses: 0,
  });

  function loadState() {
    try {
      const raw = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
      return raw && typeof raw === "object" ? { ...defaults(), ...raw } : defaults();
    } catch (_) {
      return defaults();
    }
  }

  let state = loadState();
  let lastAction = null;
  let currentSuggestion = "";
  let recognition = null;

  function persist() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }

  function tokenFor(element) {
    const target = element && element.closest
      ? element.closest("[data-action], [data-lens], button, a, select, textarea, input")
      : null;
    if (!target) return null;
    if (target.dataset && target.dataset.action) return `action:${target.dataset.action}`;
    if (target.dataset && target.dataset.lens) return `lens:${target.dataset.lens}`;
    if (target.id) return `id:${target.id}`;
    const text = String(target.textContent || target.getAttribute("aria-label") || "")
      .trim().replace(/\s+/g, " ").slice(0, 48);
    return text ? `label:${text}` : null;
  }

  function elementForToken(token) {
    if (!token) return null;
    const [kind, value] = token.split(":", 2);
    if (kind === "action") return document.querySelector(`[data-action="${CSS.escape(value)}"]`);
    if (kind === "lens") return document.querySelector(`[data-lens="${CSS.escape(value)}"]`);
    if (kind === "id") return document.getElementById(value);
    if (kind === "label") {
      return [...document.querySelectorAll("button, a")].find((item) =>
        String(item.textContent || "").trim().replace(/\s+/g, " ").startsWith(value)
      ) || null;
    }
    return null;
  }

  function recordAction(token) {
    if (!token) return;
    state.clicks[token] = Math.min(100000, Number(state.clicks[token] || 0) + 1);
    if (lastAction && lastAction !== token) {
      const key = `${lastAction}>${token}`;
      state.transitions[key] = Math.min(100000, Number(state.transitions[key] || 0) + 1);
    }
    state.recent.push({ token, at: Date.now() });
    state.recent = state.recent.slice(-MAX_RECENT);
    lastAction = token;
    persist();
    renderNextStep();
  }

  function predictedNext() {
    if (!lastAction) return null;
    const prefix = `${lastAction}>`;
    const candidates = Object.entries(state.transitions)
      .filter(([key]) => key.startsWith(prefix))
      .map(([key, count]) => ({ token: key.slice(prefix.length), count: Number(count) || 0 }))
      .sort((a, b) => b.count - a.count);
    if (!candidates[0] || candidates[0].count < 2) return null;
    return candidates[0];
  }

  function readableToken(token) {
    if (!token) return "";
    const value = token.includes(":") ? token.slice(token.indexOf(":") + 1) : token;
    return value.replace(/[-_]/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  }

  function renderNextStep() {
    const button = document.getElementById("assist-next-step");
    if (!button) return;
    const predicted = predictedNext();
    if (!predicted) {
      button.hidden = true;
      return;
    }
    button.hidden = false;
    button.dataset.targetToken = predicted.token;
    button.textContent = `Likely next · ${readableToken(predicted.token)}`;
  }

  function lensName() {
    const active = document.querySelector(".nav-item.active");
    return active && active.dataset ? active.dataset.lens || "overview" : "overview";
  }

  const contextualPrompts = {
    overview: [
      "Summarize the system and what needs my attention",
      "Show me what Aurum is working on right now",
      "What changed since my last session?",
    ],
    kernel: [
      "Show the adaptive kernel status",
      "Explain the current kernel frontier",
      "Build the safest next kernel step",
    ],
    devices: [
      "Show attached devices and their current capabilities",
      "What changed in the hardware graph?",
      "Explain any device that still needs a capability",
    ],
    memory: [
      "Show the most relevant remembered context",
      "What has Aurum learned about how I work?",
      "Summarize durable state from this session",
    ],
    builds: [
      "Show every active build lane",
      "Which build is closest to a testable artifact?",
      "Continue all unblocked build lanes in parallel",
    ],
  };

  function promptCandidates() {
    const history = Array.isArray(state.prompts) ? state.prompts.map((item) => item.text).filter(Boolean) : [];
    return [...history.reverse(), ...(contextualPrompts[lensName()] || contextualPrompts.overview)];
  }

  function updateSuggestion() {
    const prompt = document.getElementById("prompt");
    const button = document.getElementById("assist-complete");
    if (!prompt || !button) return;
    const typed = prompt.value.trim();
    const candidates = [...new Set(promptCandidates())];
    let candidate = "";
    if (typed) {
      const lower = typed.toLowerCase();
      candidate = candidates.find((item) => item.toLowerCase().startsWith(lower) && item.length > typed.length) || "";
    } else {
      candidate = candidates[0] || "";
    }
    currentSuggestion = candidate;
    if (!candidate) {
      button.hidden = true;
      return;
    }
    button.hidden = false;
    button.textContent = typed ? `Tab to complete · ${candidate}` : `Suggested · ${candidate}`;
  }

  function acceptSuggestion() {
    const prompt = document.getElementById("prompt");
    if (!prompt || !currentSuggestion) return false;
    prompt.value = currentSuggestion;
    prompt.dispatchEvent(new Event("input", { bubbles: true }));
    prompt.focus();
    state.acceptedSuggestions = Number(state.acceptedSuggestions || 0) + 1;
    persist();
    return true;
  }

  function rememberPrompt(text) {
    const clean = String(text || "").trim();
    if (!clean) return;
    const existing = state.prompts.find((item) => item.text === clean);
    if (existing) {
      existing.count = Number(existing.count || 0) + 1;
      existing.lastUsed = Date.now();
    } else {
      state.prompts.push({ text: clean, count: 1, lastUsed: Date.now() });
    }
    state.prompts.sort((a, b) => (b.count - a.count) || (b.lastUsed - a.lastUsed));
    state.prompts = state.prompts.slice(0, MAX_PROMPTS);
    persist();
  }

  function injectAssistUI() {
    const composer = document.getElementById("composer");
    if (!composer || document.getElementById("assist-strip")) return;

    const voice = document.createElement("button");
    voice.type = "button";
    voice.id = "assist-voice";
    voice.className = "assist-voice";
    voice.setAttribute("aria-label", "Speak prompt");
    voice.textContent = "Voice";
    const send = document.getElementById("send");
    composer.insertBefore(voice, send || null);

    const strip = document.createElement("div");
    strip.id = "assist-strip";
    strip.className = "assist-strip";
    strip.innerHTML = [
      '<button type="button" id="assist-complete" class="assist-chip" hidden></button>',
      '<button type="button" id="assist-next-step" class="assist-chip" hidden></button>',
      '<span class="assist-note">Context help is suggested, never auto-executed.</span>',
    ].join("");
    const note = composer.nextElementSibling;
    if (note) note.after(strip); else composer.after(strip);
  }

  function setupVoice() {
    const button = document.getElementById("assist-voice");
    if (!button) return;
    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Recognition) {
      button.disabled = true;
      button.title = "Speech recognition is not available in this browser";
      return;
    }
    recognition = new Recognition();
    recognition.lang = navigator.language || "en-US";
    recognition.interimResults = true;
    recognition.continuous = false;

    recognition.addEventListener("start", () => {
      button.classList.add("listening");
      button.textContent = "Listening…";
      state.voiceUses = Number(state.voiceUses || 0) + 1;
      persist();
    });
    recognition.addEventListener("result", (event) => {
      const transcript = [...event.results].map((result) => result[0].transcript).join(" ").trim();
      const prompt = document.getElementById("prompt");
      if (prompt && transcript) {
        prompt.value = transcript;
        prompt.dispatchEvent(new Event("input", { bubbles: true }));
      }
    });
    recognition.addEventListener("end", () => {
      button.classList.remove("listening");
      button.textContent = "Voice";
    });
    recognition.addEventListener("error", () => {
      button.classList.remove("listening");
      button.textContent = "Voice";
    });
    button.addEventListener("click", () => {
      try { recognition.start(); } catch (_) { /* already active */ }
    });
  }

  function wire() {
    injectAssistUI();
    setupVoice();

    document.addEventListener("click", (event) => {
      const token = tokenFor(event.target);
      if (token && !String(token).startsWith("id:prompt")) recordAction(token);
    }, true);

    const prompt = document.getElementById("prompt");
    if (prompt) {
      prompt.addEventListener("input", updateSuggestion);
      prompt.addEventListener("keydown", (event) => {
        if (event.key === "Tab" && currentSuggestion) {
          event.preventDefault();
          acceptSuggestion();
        }
      });
    }

    const complete = document.getElementById("assist-complete");
    if (complete) complete.addEventListener("click", acceptSuggestion);

    const next = document.getElementById("assist-next-step");
    if (next) {
      next.addEventListener("click", () => {
        const target = elementForToken(next.dataset.targetToken || "");
        if (!target) return;
        target.scrollIntoView({ behavior: "smooth", block: "center" });
        target.classList.add("aurum-next-highlight");
        target.focus({ preventScroll: true });
        setTimeout(() => target.classList.remove("aurum-next-highlight"), 1600);
      });
    }

    const composer = document.getElementById("composer");
    if (composer) {
      composer.addEventListener("submit", () => {
        if (prompt) rememberPrompt(prompt.value);
      }, true);
    }

    updateSuggestion();
    renderNextStep();
  }

  window.AurumInteraction = {
    snapshot: () => JSON.parse(JSON.stringify(state)),
    recent: () => [...state.recent],
    reset: () => { state = defaults(); lastAction = null; persist(); updateSuggestion(); renderNextStep(); },
  };

  document.addEventListener("DOMContentLoaded", wire);
})();
