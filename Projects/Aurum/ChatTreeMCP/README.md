# Aurum Chat Tree MCP

A small **tool-only MCP adapter** for the canonical BoxBrain Chat Tree and shared-state bus.

It does not replace the Chat Tree, Future Branch, or the evidence journal. It gives ChatGPT/MCP-capable clients a narrow interface to the same durable state used by BoxBrain processes.

## Tools

| Tool | Purpose | Mutation |
| --- | --- | --- |
| `get_tree` | Read the durable conversation/process tree and focus path. | No |
| `get_state` | Read evidence-backed live state. | No |
| `read_live_state` | Consume the newest status/current action/blocker/evidence/next action from the append-only bus, with optional filtered history. | No |
| `plan_consolidation` | Find terminal nodes with the exact same parent group and lane. | No |
| `consolidate_branch` | Create a provenance checkpoint and archive the reviewed source tree nodes. | Yes, tree only; approval-gated |
| `route_topic` | Continue the current topic or materialize a child/sibling split. | Yes, tree only |
| `post_receipt` | Append a process/device evidence receipt and refresh the projection. | Yes, state journal |
| `publish_live_state` | Publish a chat/process status/current action/blocker/evidence/next action update. | Yes, state journal |
| `dispatch_farmer_objective` | Dispatch a bounded objective to the fixed Farmer GitHub controller. | Yes, external event only |

`running_verified` and `succeeded` receipts require evidence references. The MCP
server never grants arbitrary execution authority and never erases physical/LKG
boundaries. Its only execution action is the v3.2 Farmer actuator, which rejects
repository, URL, workflow, token, code, command, and arbitrary payload fields.
Set `GITHUB_TOKEN` or the server-owned `AURUM_FARMER_GITHUB_TOKEN_FILE`; neither
credential is ever returned to clients.

`publish_live_state` requires the five cross-chat continuity fields on every
update: `status`, `current_action`, `blocker` (which may be null), `evidence`, and
`next_action`. The consumer reads the journal rather than chat memory and marks
whether the returned runtime status is one of the evidence-required verified
states. Multiple publisher processes coordinate through a journal lock; the
projection is replaced atomically while prior JSONL events remain untouched.

Consolidation matching is intentionally strict: every source must be completed or failed and must share the exact same `parent_id` and `lane_id`. Sources are marked archived but retained with `merged_from` provenance. The plugin cannot archive the corresponding conversations in ChatGPT's own History; it only changes the canonical Aurum tree.

## Run locally

From the repository root:

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r Projects/Aurum/ChatTreeMCP/requirements.txt
python Projects/Aurum/ChatTreeMCP/main.py
```

The service exposes:

- MCP: `http://localhost:8000/mcp`
- health: `http://localhost:8000/healthz`

The default storage is the repository's canonical:

- `Projects/Aurum/chat-process-tree.json`
- `Projects/Aurum/shared-state/events.jsonl`
- `Projects/Aurum/shared-state/CURRENT_STATE.json`

Override them for a persistent/runtime state location with:

- `CHAT_TREE_TREE_PATH`
- `CHAT_TREE_EVENTS_PATH`
- `CHAT_TREE_PROJECTION_PATH`

## Connect to ChatGPT for development

ChatGPT needs an HTTPS-reachable MCP endpoint. Expose port 8000 with your preferred secure tunnel, then register the resulting `/mcp` endpoint in the current ChatGPT developer/connectors flow.

When tunneling, set the Python MCP transport allowlists before starting the server:

```bash
MCP_ALLOWED_HOSTS=<your-tunnel-host>
MCP_ALLOWED_ORIGINS=https://<your-tunnel-host>
```

Then point the connector at:

```text
https://<your-tunnel-host>/mcp
```

This adapter does **not** directly control ChatGPT's native sidebar. BoxBrain owns the canonical tree; a later Chat Tree widget/sidebar-capable surface can render this same state without changing the underlying model.

## Validation

```bash
cd Projects/Aurum/ChatTreeMCP
python -m unittest -v test_server.py
```

CI compiles the server, installs current MCP SDK v2 dependencies, runs these adapter tests, and re-runs the core Chat Tree/shared-state regression suite.

## Source of truth

The server delegates to:

- `../Experiments/chat_tree_bridge.py`
- `../Experiments/chat_topic_router.py`
- `../Experiments/chat_process_tree.py`
- `../Experiments/shared_state_bus.py`

That keeps ChatGPT, Future Branch, runners, and BoxBrain processes on one state model instead of creating a new plugin-specific memory silo.

The registered Bluehost endpoint uses the source-controlled
[PHP compatibility adapter](../ChatTreePlugin/deploy/README.md) while delegating
to these same bridge and state-bus modules.
