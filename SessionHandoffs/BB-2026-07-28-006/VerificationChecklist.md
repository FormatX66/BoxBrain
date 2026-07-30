# Verification Checklist

- [x] Searched the project, decision, integration, and prior handoff indexes
  before creating session 006.
- [x] Created no duplicate repository, protocol, architecture, or target
  document.
- [x] Fixed arguments and bounded schema version 1 JSON are enforced.
- [x] FreeRDP external certificate management is enabled.
- [x] Only server-selected NLA/HYBRID permits certificate observation.
- [x] TLS-only selection fails with no JSON.
- [x] Every presented certificate is rejected before authentication.
- [x] Authentication and `PostConnect` callbacks fail the probe.
- [x] No TLS application data, credential, desktop session, channel, frame,
  input, clipboard, file, shell, or device-redirection path is reached.
- [x] Internal deadline exit code 124 maps to the controller timeout error.
- [x] Native amd64 build: 2 CTest tests passed.
- [x] Native arm64 build: 2 CTest tests passed.
- [x] BrainConnect controller tests: 27 passed.
- [x] BrainConnect Python compilation passed.
- [x] BrainConnect Flutter analysis: no issues found.
- [x] BrainConnect Flutter tests: 8 passed.
- [x] BrainConnect production Flutter web build succeeded.
- [x] BrainConnect `git diff --check` passed.
- [x] BrainConnect commit created and pushed: `01c34d7`.
- [x] BrainConnect draft review opened as pull request 4.
- [x] BoxBrain structural and Markdown-link validation passes.
- [x] BoxBrain documentation commit is pushed to pull request 3.
- [x] Both repository working trees are clean.
