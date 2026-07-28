# Questions — BB-2026-07-28-002

1. Should the first observation-only transport use RDP or VNC?
2. Which target identity is authoritative: configured UUID, certificate
   fingerprint, VM provider ID, network endpoint, or a combination?
3. Who may add, enable, disable, or rotate an allowlisted target?
4. How long may screenshots and observation metadata be retained?
5. Should stream reconnect use bounded exponential backoff before the first
   remote deployment?
6. When should the local feature branch be merged into `main`?

Only the target identity and retention questions block the observation plugin.
