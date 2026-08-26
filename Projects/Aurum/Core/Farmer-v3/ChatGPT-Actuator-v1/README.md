# Aurum Farmer ChatGPT Actuator v1

This closes the missing execution boundary between the Aurum Chat Tree MCP surface and the tested Aurum Farmer GitHub controller.

## New MCP action

`dispatch_farmer_objective(objective_id, objective)`

The action is deliberately narrower than a shell/command tool. It accepts only an objective identifier and natural-language objective. Repository, GitHub event type, completion definition, safety invariants, and continuation model are server-owned constants.

The action dispatches a fixed GitHub `repository_dispatch` event named `aurum_farmer_event` to `FormatX66/Chat-to-Git-Pipeline` (or the server-owned `AURUM_FARMER_REPOSITORY`). The tested Farmer controller then owns continuation through executor/verifier receipts.

## Security invariants

- No shell, command, code, repository, URL, token, workflow, or arbitrary payload fields are accepted from ChatGPT.
- GitHub token is server-side only.
- Missing/broken GitHub authority returns a machine blocker with `human_required=false`.
- Dispatch never equals completion. It returns a GitHub ingress receipt; Farmer's independent verifier owns `verified_completion`.
- No timers/polling are introduced.

## Integrating into Aurum Chat Tree MCP

1. Add `FARMER_TOOL` to the MCP `tools/list` response.
2. In `tools/call`, route `dispatch_farmer_objective` to `handleFarmerToolCall`.
3. Provide `GITHUB_TOKEN` with Actions/repository-dispatch write authority and optionally `AURUM_FARMER_REPOSITORY`.
4. Deploy the updated MCP endpoint.
5. From ChatGPT, call the new action with a harmless objective and verify a GitHub `aurum_farmer_event` controller run appears.
6. Verify the controller continues via receipts to a terminal Farmer state without another ChatGPT/user prompt.

The existing six Chat Tree actions remain state/navigation only. This seventh action is the bounded execution actuator.
