# Aurum Local Lane

This lane exists so a ChatGPT/GitHub session can request a narrowly bounded BBPI4 Aurum deploy or verification without asking the operator to manually relay every command.

## Authority boundary

The locally installed watcher accepts only the exact JSON task schema in `.codex/local-lane/AURUM_TASK.json` and only these actions:

- `deploy`
- `verify`

The target is fixed to `BBPI4` at `192.168.0.194`. The existing dedicated key is fixed to `%USERPROFILE%\.ssh\boxbrain_pi_ed25519`. Task data cannot supply commands, scripts, paths, arguments, credentials, alternate hosts, or alternate users.

Installation copies the watcher into LocalAppData and records SHA-256 approval for the watcher, the Aurum deployer, and the complete `Projects/Codelation` source tree. A later Git change to executable deployment code or Codelation source does not inherit local execution authority; the lane fails closed until the operator deliberately reinstalls/reapproves it.

The watcher writes only `.codex/local-lane/AURUM_RESULT.json` back to Git. Results are bounded and include verification markers rather than credentials or private-key material. A local pending-result checkpoint prevents a transient Git push failure from repeating a successful deployment.

## One-time install

From the BoxBrain repository root on the already-authorized Windows host:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\installer\install-aurum-local-lane.ps1 -ApproveAurumLane -StartNow
```

After this one local approval, future bounded Aurum deploy/verify requests can be published through Git by updating `AURUM_TASK.json`. The watcher polls once per minute by default and returns the result through `AURUM_RESULT.json`.
