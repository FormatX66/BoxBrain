# Verification Checklist

- [x] Searched current project, decision, integration, roadmap, and session
  indexes before creating session 008.
- [x] Created no duplicate repository, architecture, deployment, or protocol
  document.
- [x] Confirmed no prior Pi controller user, release, state, configuration, or
  systemd unit existed before deployment.
- [x] Confirmed Kali arm64, Python 3.13.12, systemd 260, free storage, DNS, and
  port availability.
- [x] Exact Python runtime lock installed and imported on ARM64.
- [x] Installed helper checksum matched the required provenance.
- [x] Controller wheel and deployment provenance recorded.
- [x] Authenticated foreground health gate passed before service enablement.
- [x] Service runs as the dedicated non-login `brainconnect` account.
- [x] Service is enabled and active.
- [x] Listener is exactly `10.12.194.1:8000`, not Wi-Fi or all interfaces.
- [x] Windows-to-Pi unauthenticated health returned HTTP 401.
- [x] Token and SQLite database are mode `0600` in a mode `0700` directory.
- [x] Token is absent from Git and the systemd environment file.
- [x] Emergency stop survived an engaged restart and a released restart.
- [x] Installed helper hash was reverified as the service user.
- [x] systemd unit verification passed.
- [x] `systemd-analyze security` reported exposure `2.8 OK`.
- [x] No operating-system package or firewall rule changed.
- [x] No RDP target, credential, authentication, desktop session, frame, input,
  shell, clipboard, file, or device redirection was exercised.
- [x] BrainConnect controller tests: 27 passed.
- [x] BrainConnect Python compilation passed.
- [x] BrainConnect Flutter analysis: no issues found.
- [x] BrainConnect Flutter tests: 8 passed.
- [x] BrainConnect production Flutter web build succeeded.
- [x] BrainConnect branch pushed at `ee9c518`.
- [x] BrainConnect draft review opened as pull request 6.
- [x] BoxBrain structural and Markdown-link validation passes.
- [x] BoxBrain documentation commit is pushed to pull request 3.
- [x] Both repository working trees are clean.
