# Change Log

## BrainConnect

- **Changed files:** Native input protocol, request parser, FreeRDP keyboard and
  pointer connector, systemd credential provider, native unit/integration
  tests, Docker build, Pi promotion and experiment scripts, controller
  deployment compatibility, and canonical README, architecture, development,
  open-lab, roadmap, security, target, plugin, and installer documentation.
- **Reason:** Promote the reviewed connector to the Pi, add bounded keyboard
  input, exercise an exact-target live run, fix runtime compatibility, and
  restore the controller to an inert credential-free state.
- **Dependencies:** BrainConnect durable operation boundary, pinned RDP target,
  FreeRDP 3.26 runtime, systemd credentials, disposable Windows VM, and
  restricted guest diagnostic link.
- **Future implications:** The transport path is proven, but a persistent
  session and independent verifier are required before declaring durable UI
  control.

## BoxBrain

- **Changed files:** Admin decision, change, session, roadmap, TODO, and
  repository indexes; system architecture, data flow, and integrations;
  BrainConnect project index; project registry; handoff index; and this session
  bundle.
- **Reason:** Preserve the exact Pi artifact and rollback state, live operation
  evidence, truthful success boundary, remaining Hyper-V blocker, and next
  execution order.
- **Dependencies:** BrainConnect commit `e81f5f5` and draft pull request 11.
- **Future implications:** The next session can start at visual verification
  instead of repeating credential promotion or transport debugging.
