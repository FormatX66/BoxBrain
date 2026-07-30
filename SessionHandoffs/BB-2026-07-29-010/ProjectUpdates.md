# Project Updates

## BrainConnect

- **Status:** Active alpha
- **Completion:** 98% planning estimate
- **Current revision:** `f4461d2`
- **Installed revision:** `567ffa3`
- **Installed control SHA-256:**
  `090929ac598855b5da72732a08975a291fa84d4cfbb718585665c8c747c5077e`
- **Verified now:** Exact target identity, standard-session readiness,
  protocol-clean native results, bounded frames, visible text,
  coordinate-bound click effect, Pi cleanup, rotated credential, new
  checkpoint creation/restoration, and final unauthenticated certificate
  match.
- **Pending:** Upgrade-state preflight, FreeRDP build/runtime alignment or
  continued compatibility gate, shell, scrolling, clipboard, and generalized
  per-action verification.

## BoxBrain

- Added the reviewed credential-rotation helper.
- Recorded decisions BB-ADR-034 through BB-ADR-038.
- Marked bounded frame and coordinate-click proof complete.
- Replaced the old checkpoint as the active recovery point.
- Preserved BrainConnect as the canonical implementation repository.

## Related projects

- **Security:** Credential incident response and bounded image retention are
  now exercised controls.
- **Research:** Visible click and keyboard outcomes can become regression
  benchmark cases.
- **AgentFramework:** Planner integration remains downstream of generalized
  operation verification.
