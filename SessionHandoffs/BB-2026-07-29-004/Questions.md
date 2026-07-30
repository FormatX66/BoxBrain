# Questions

1. Which transport should implement the first live adapter: FreeRDP input,
   PowerShell Direct, or a separate guest-side agent? The choice must preserve
   the same target/session identity boundary.
2. Where should the disposable RDP credential be supplied at runtime so it can
   be rotated without entering BrainConnect state or logs?
3. Should the first live operation be a read-only shell command, pointer move,
   or keyboard action?
4. What evidence is sufficient to verify each operation without storing
   sensitive full-screen frames?
5. Should queued operations be cancelled automatically when the target is
   disabled or its certificate changes?
6. When may the detached answer ISO containing the one-time lab password be
   removed?
