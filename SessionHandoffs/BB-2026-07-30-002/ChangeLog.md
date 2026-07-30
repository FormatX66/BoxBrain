# Change Log

## Changed files

- BrainConnect: added `.gitattributes`, LF-safe controller deployment,
  deterministic alpha scrolling proof, focused fixture validation, and
  completed alpha documentation.
- BoxBrain: allowed the established Hyper-V operator group to run the exact
  checkpoint helper; updated BrainConnect status, roadmap, TODOs, indexes,
  decisions, and this session bundle.

## Reason

The final alpha gates exposed one Windows line-ending portability defect and
one unnecessary elevation assumption. Both were repaired before the live
scrolling acceptance run.

## Dependencies

- FreeRDP 3.15 reproducible build image
- Pi FreeRDP 3.26 runtime
- Exact target certificate
- Rotated disposable-VM checkpoint

## Future implications

Remote scripts must remain line-ending independent. Future live capabilities
must provide bounded independent effect evidence and restore the same inert
baseline.
