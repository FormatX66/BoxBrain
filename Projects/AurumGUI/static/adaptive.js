(() => {
  "use strict";

  const STORAGE_KEY = "aurum.ui.adaptation.v0";
  const SESSION_KEY = "aurum.ui.environment-observed.v0";
  const PROFILES = new Set(["aurum", "windows", "macos", "touch"]);

  const defaults = () => ({
    mode: "auto",
    profile: "aurum",
    evidence: { aurum: 0, windows: 0, macos: 0, touch: 0 },
    lensUsage: { overview: 0, kernel: 0, devices: 0, memory: 0, builds: 0 },
    revision: 0,
  });

  function loadState() {
    try {
      const raw = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
      if (!raw || typeof raw !== "object") return defaults();
      const next = defaults();
      if (raw.mode === "auto" || raw.mode === "locked") next.mode = raw.mode;
      if (PROFILES.has(raw.profile)) next.profile = raw.profile;
      for (const key of PROFILES) {
        const value = Number(raw.evidence && raw.evidence[key]);
        if (Number.isFinite(value) && value >= 0) next.evidence[key] = value;
      }
      for (const key of Object.keys(next.lensUsage)) {
        const value = Number(raw.lensUsage && raw.lensUsage[key]);
        if (Number.isFinite(value) && value >= 0) next.lensUsage[key] = value;
      }
      next.revision = Number.isFinite(Number(raw.revision)) ? Number(raw.revision) : 0;
      return next;
    } catch (_) {
      return defaults();
    }
  }

  let state = loadState();

  function persist() {
    state.revision += 1;
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }

  function bestProfile() {
    const ranked = Object.entries(state.evidence).sort((a, b) => b[1] - a[1]);
    const [best, score] = ranked[0];
    const second = ranked[1] ? ranked[1][1] : 0;
    if (score < 2) return state.profile;
    if (score - second < 1 && state.profile !== "aurum") return state.profile;
    return best;
  }

  function applyProfile() {
    const profile = state.mode === "auto" ? bestProfile() : state.profile;
    state.profile = PROFILES.has(profile) ? profile : "aurum";
    document.documentElement.dataset.uiProfile = state.profile;
    document.documentElement.dataset.uiMode = state.mode;

    const select = document.getElementById("ui-profile");
    if (select) select.value = state.mode === "auto" ? "auto" : state.profile;

    const label = document.getElementById("ui-learning-state");
    if (label) {
      const name = state.profile === "windows" ? "Windows-like"
        : state.profile === "macos" ? "macOS-like"
        : state.profile === "touch" ? "Touch"
        : "Aurum";
      label.textContent = state.mode === "auto" ? `learning · ${name}` : `locked · ${name}`;
    }

    applyLearnedNavigation();
  }

  function observe(profile, weight = 1) {
    if (!PROFILES.has(profile) || state.mode !== "auto") return;
    state.evidence[profile] = Math.min(100, state.evidence[profile] + weight);
    persist();
    applyProfile();
  }

  function observeEnvironmentOnce() {
    if (sessionStorage.getItem(SESSION_KEY) === "1") return;
    sessionStorage.setItem(SESSION_KEY, "1");

    const platform = String(
      (navigator.userAgentData && navigator.userAgentData.platform) || navigator.platform || ""
    ).toLowerCase();
    if (platform.includes("win")) observe("windows", 3);
    if (platform.includes("mac")) observe("macos", 3);
    if ((navigator.maxTouchPoints || 0) > 0) observe("touch", 1);
  }

  function applyLearnedNavigation() {
    const nav = document.querySelector(".nav");
    if (!nav || state.mode !== "auto") return;
    const total = Object.values(state.lensUsage).reduce((sum, value) => sum + value, 0);
    if (total < 8) return;

    const items = [...nav.querySelectorAll(".nav-item")];
    const overview = items.find((item) => item.dataset.lens === "overview");
    const rest = items
      .filter((item) => item !== overview)
      .sort((a, b) => (state.lensUsage[b.dataset.lens] || 0) - (state.lensUsage[a.dataset.lens] || 0));
    if (overview) nav.appendChild(overview);
    rest.forEach((item) => nav.appendChild(item));
  }

  function recordLens(lens) {
    if (!(lens in state.lensUsage)) return;
    state.lensUsage[lens] = Math.min(10000, state.lensUsage[lens] + 1);
    persist();
    applyLearnedNavigation();
  }

  function wireControls() {
    const select = document.getElementById("ui-profile");
    if (select) {
      select.addEventListener("change", () => {
        const value = select.value;
        if (value === "auto") {
          state.mode = "auto";
        } else if (PROFILES.has(value)) {
          state.mode = "locked";
          state.profile = value;
        }
        persist();
        applyProfile();
      });
    }

    const reset = document.getElementById("ui-reset");
    if (reset) {
      reset.addEventListener("click", () => {
        state = defaults();
        persist();
        applyProfile();
        observeEnvironmentOnce();
      });
    }

    document.querySelectorAll(".nav-item").forEach((item) => {
      item.addEventListener("click", () => recordLens(item.dataset.lens || "overview"));
    });

    window.addEventListener("pointerdown", (event) => {
      if (event.pointerType === "touch") observe("touch", 0.15);
    }, { passive: true });
  }

  document.documentElement.dataset.uiProfile = state.profile;
  document.addEventListener("DOMContentLoaded", () => {
    wireControls();
    observeEnvironmentOnce();
    applyProfile();
  });
})();
