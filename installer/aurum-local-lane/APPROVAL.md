# Aurum Local Lane Approval Summary

Local approval authorizes exactly one installed watcher with these fixed boundaries:

- Repository: `FormatX66/BoxBrain`
- Target: `BBPI4`
- Address: `192.168.0.194`
- User: `kali`
- Key path: `%USERPROFILE%\.ssh\boxbrain_pi_ed25519`
- Allowed actions: `deploy`, `verify`
- Allowed deployer: the locally SHA-256-pinned `installer/deploy-aurum-live-to-pi.ps1`
- Allowed payload: the locally SHA-256-pinned complete `Projects/Codelation` tree
- Result path: `.codex/local-lane/AURUM_RESULT.json`

The task file cannot provide shell text, arguments, alternate paths, credentials, hosts, users, or executable content. Any change to the watcher, deployer, or Codelation source requires a new local reinstall/approval before deployment authority resumes.
