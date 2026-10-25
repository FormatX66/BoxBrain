# Decision Log — BB-2026-08-15-001

## BB-ADR-061

### Decision

Select the original detailed `Au` codelation emblem as Bruce's first personalized Aurum logo. Preserve the exact selected PNG and its SHA-256 digest as the geometry authority. Do not allow a later generative redraw to replace it silently.

### Context

Bruce asked Aurum and Codex to choose rather than merely mirror his taste. Four candidates were compared: the original emblem, a transparent regeneration, a flatter generated reinterpretation, and a deterministic seven-lane compact derivative. Aurum independently selected the original. Codex reached the same conclusion. Bruce then confirmed the converged choice and clarified that his own liking for the mark was feedback, not the motive for the selection.

Later generations showed early identity drift: altered proportions, ambiguous terminals, duplicated or weakened node meaning, and loss of deliberate codelation structure. This made recency an unreliable selection signal.

### Consequences

- `Projects/Codelation/assets/identity/bruce-aurum-personal-logo-selected.png` is the selected source.
- Its required SHA-256 is `cc6f724146cee4df50146cf9ab4d78e3ccdc6b2a62b3c72116ded90bb24b304d`.
- The baked checkerboard is a production defect and may be removed mechanically.
- Any vector trace or small-size derivative must be reviewed against the selected source.
- The personal mark does not replace the universal Aurum identity without another explicit decision.
- The proven selection workflow and the generative-identity-drift failure pattern are stored in the repository-first memory stack.
