# BoxBrain / Aurum Agent Instructions

These instructions apply to every agent, coding assistant, automation author,
and troubleshooting session operating in this repository.

## Mandatory state-first execution

Use [Architecture/ExecutionLogic.md](Architecture/ExecutionLogic.md) as the
default execution policy.

Before meaningful action, proportionally determine:

`intent -> observed current state -> required state -> delta -> constraints -> minimum useful action -> verification`

Do not execute work merely because a prompt arrived. An action must either
change a state required by the user's outcome or produce genuinely new evidence.
If neither is possible, do not spend compute/usage performing it.

## Required behavior

- Treat a short, imperfect, or generic prompt as directional evidence against the
  active project state, not as a context reset. Infer the likely required outcome,
  execute safe reversible work shared by plausible intents, and ask only when the
  remaining answer changes the route or crosses a real human boundary. Inferred
  intent never grants protected authority.
- Prefer cached verified evidence and deterministic local work before model calls.
- Deduplicate equivalent work and never replay a known state without a changed input, implementation, environment, evidence, hypothesis, dependency, or authority.
- Distinguish `success`, `waiting`, `refused`, `blocked`, `no_change`, and `failed`.
- Expected waiting/refusal/no-change states must not become false-red workflow failures.
- Verify results from the machine/runtime; command completion alone is not proof.
- Preserve provenance for consequential actions and reasoning.
- Heartbeats, timestamps, counters, iteration numbers, and receipt updates are not semantic progress by themselves.
- Do not turn a verified deployment/build into a failure because later bookkeeping publication failed.
- Fix repeated failures at the earliest shared invariant instead of adding retries around the symptom.
- Escalate to the user only for a real human decision, credential, permission, destructive authorization, subjective choice, or unavailable external fact.

## Aurum-specific invariant

Aurum progression is expressed as capability + evidence + unresolved frontier +
events. Repeated cycles, generations, timestamps, or heartbeats are not progress.
Aurum must discover what works rather than repeatedly attempt to prove a preferred
implementation correct.
