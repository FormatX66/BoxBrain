# Project Updates

## BrainConnect

- **Status:** Active alpha
- **Priority:** P0
- **Completion:** 94% planning estimate
- **Revision:** `d207694` on `feature/brainconnect-freerdp-control`
- **Review:** [Draft pull request 10](https://github.com/FormatX66/BrainConnect/pull/10)
- **Complete:** Native absolute-pointer connector, exact post-pin credential
  lookup, target-UUID systemd credential contract, no-redirection settings,
  canonical request/result protocol, credential hardening, amd64/arm64 builds,
  and certificate/credential sequencing fixtures.
- **Not deployed:** The Pi remains on the prior controller revision with no
  control binary, no RDP credential, and `executor_enabled = false`.
- **Next:** Consolidated Pi installer, on-host negative fixtures, encrypted
  credential provision, independent cursor evidence, one live pointer action,
  disablement, and checkpoint restoration.

## Related projects

- **Security:** Systemd credential naming, no-follow file checks, and post-pin
  lookup are candidates for shared runtime-secret guidance.
- **Research:** Accepted-event versus visually verified-state should become
  separate benchmark outcomes.
- **AgentFramework:** Planners still see the broader typed queue, but runtime
  capability discovery must prevent proposals from assuming unimplemented
  operations can execute.
- **Automation:** Artifact promotion, service drop-in rollback, and checkpoint
  restore form the next reusable workflow.
