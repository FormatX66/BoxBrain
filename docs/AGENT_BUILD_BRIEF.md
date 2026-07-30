# BoxBrain Model-Agent Build Brief

## Confirmed requirements

- Intake arrives as rough voice transcripts, chat, API text, or files.
- The main crew is Orchestrator, Quartermaster, Sentinel, Librarian,
  Archivist, Scout, Task Manager, Architect, Engineer, and Integrator.
- Local project memory and task state are authoritative and durable.
- Provider usage must be visible and bounded.
- External changes such as sending, publishing, deploying, or deleting require
  explicit approval.
- The existing deterministic processing endpoint must remain available.

## Implementation decision

Add one focused OpenAI Agents SDK orchestrator with typed output. It converts
messy intake plus local context into a grounded plan. The existing deterministic
crew remains the persistence and safety layer, so the model cannot directly
perform connector, device, shell, or deployment actions.

The model-backed endpoint returns:

- the durable local processing run;
- a typed orchestration plan with summary, decisions, tasks, specialist
  handoffs, and risk flags;
- provider/runtime metadata that never includes credentials.

The existing Flutter dashboard exposes the crew, runtime readiness, local
workspace totals, durable tasks, and a voice/chat intake composer. Local mode is
the safe default; model reasoning is an explicit opt-in.

## Runtime contract

- Default model: `gpt-5.6-sol`, configurable with `BOXBRAIN_AGENT_MODEL`.
- Runtime switch: `BOXBRAIN_AGENT_RUNTIME_ENABLED`.
- Credential: `OPENAI_API_KEY` loaded from the process environment or ignored
  repository-local `.env.local`.
- No model call occurs on deterministic `/processing/runs`.
- No model tool has side effects.
- A missing SDK, disabled runtime, or missing key produces a clear unavailable
  response and does not affect the deterministic path.

## Verification

- Unit tests inject a fake runner and never call the provider.
- API tests verify runtime status, structured output, and unavailable behavior.
- A small explicit smoke command verifies the configured provider path.
- The full controller suite must still pass.

## Verification result

- All 61 controller tests and all 9 Flutter tests pass.
- The authenticated dashboard build includes the Agents workspace and is served
  locally over HTTPS.
- The live request reached OpenAI and was correctly classified as
  `insufficient_quota`; the API project needs billing credit or a higher usage
  limit before a successful provider response can complete.
