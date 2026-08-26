# Chat Process Tree

Human chat is usually linear because a person needs one readable focus at a time.
Machine work is not linear. Aurum therefore keeps a durable process tree behind
the focused conversation instead of discarding every branch that is not currently
being discussed.

The tree is paired with an evidence-backed shared state bus. The tree answers
**where does this work belong?** The state bus answers **what is actually true
right now, and what proves it?** Chat memory is useful context but is not the live
source of truth.

## Model

```text
conversation root
  ├─ chat lane: Chat Tree / conversation routing
  │    ├─ child: GPT bridge
  │    └─ child: dashboard/sidebar projection
  ├─ chat lane: Pi3 adaptive driver tests
  │    ├─ process: physical Pi3 bring-up
  │    └─ process: digital twin/QPU correlation
  └─ process lane: Hopper reachability
       └─ evidence / blocker / recovery checkpoints

shared state bus
  ├─ append-only events / receipts
  ├─ latest-state projection per subject
  ├─ evidence references
  └─ dependencies / provenance
```

Each node has one primary parent so the human can follow a clean breadcrumb path.
Dependencies and `merged_from` links turn that display tree into a provenance DAG
without destroying the readable hierarchy.

Nodes retain:

- lane and state;
- pinned concepts;
- dependencies and evidence references;
- state history;
- unresolved physical, credential, destructive, or preference boundaries;
- merge provenance.

## Topic-boundary rule

Changing ideas is a routing event, not a context reset.

Every material incoming objective is classified as exactly one of:

- `continue` — same objective; remain in the current chat/node;
- `child_split` — a real subproblem of the current objective; create a child node;
- `sibling_split` — a materially different objective; create a sibling/new chat node.

The deterministic implementation is
`Projects/Aurum/Experiments/chat_topic_router.py`. An upstream GPT or agent may
provide a `same`, `subproblem`, or `new` relation hint, but the router also has an
auditable token/concept-overlap fallback so topic splitting does not require a
model call.

A split must preserve a compact handoff: objective, relevant concepts, dependencies,
evidence references, blockers/boundaries, and shared-state references. It must not
copy unrelated conversation baggage merely because it happened earlier in the same
human chat.

### Human-facing behavior

- If the user changes to a materially new project/topic, suggest or create a sibling
  node/chat surface rather than stretching one conversation indefinitely.
- If the new work is a subproblem, nest it under the active topic.
- Returning to a prior topic resumes its existing node; it does not manufacture a
  duplicate lane.
- Chat focus may move, but sibling machine processes remain independently active,
  waiting, blocked, or complete.

The native ChatGPT sidebar is not controlled by BoxBrain. BoxBrain therefore owns
the canonical tree and can project it into its dashboard/GPT bridge now; a future
ChatGPT App/sidebar-capable surface can render the same durable nodes without
changing the underlying model.

## Shared live-state bus

`Projects/Aurum/Experiments/shared_state_bus.py` defines the transport-neutral
state/event contract. Producers can be chats, Future Branch, GitHub runners,
physical devices, local agents, or dashboard services.

The initial implementation is intentionally portable:

```text
Projects/Aurum/shared-state/events.jsonl       # append-only receipts/events
Projects/Aurum/shared-state/CURRENT_STATE.json # deterministic latest projection
```

Each event includes subject, actor, source, timestamp, status, optional tree node,
dependencies, confidence, payload, and evidence references.

Runtime state vocabulary includes:

- `planned`
- `queued`
- `running_unverified`
- `running_verified`
- `waiting`
- `blocked`
- `succeeded`
- `failed`
- `no_change`
- `refused`

`running_verified` and `succeeded` require evidence references. This prevents a
chat or controller from converting an intention, dispatched command, or stale
memory into a false claim that a device/process is actually running or complete.

The state bus records facts and provenance; it never grants execution authority.

## GPT / process bridge

`Projects/Aurum/Experiments/chat_tree_bridge.py` is the first lightweight GPT-facing
bridge. It accepts one JSON request on stdin and returns JSON on stdout. Current
commands are:

- `get_tree`
- `get_state`
- `route_topic`
- `post_receipt`

That same narrow interface can be wrapped later by a ChatGPT App/MCP tool, HTTP
service, GitHub Action, local BoxBrain agent, or voice pipeline. Keeping the core
transport-neutral avoids making conversation continuity depend on any one UI or
provider.

## Future Branch integration

Future Branch consumes both structures:

1. Read the current focus node and sibling frontier.
2. Read verified shared state and unresolved subjects.
3. Keep safe/high-value sibling branches warm even when human focus moves.
4. Route a materially new objective into a child/sibling node before long-running
   work makes unrelated context inseparable.
5. Let receipts/events wake dependent lanes.
6. Never promote predicted state into verified state without evidence.
7. Preserve LKG, State Guardian, authority, privacy, and physical-boundary rules.

Example:

```text
Pi3 physical runner -> PI3 running_verified receipt
                    -> shared state projection changes
                    -> adaptive-kernel lane dependency becomes ready
                    -> Future Branch warms digital-twin comparison
                    -> dashboard/GPT reads the same evidence-backed state
```

## Operating rules

1. Human focus changes the visible path, not the machine frontier.
2. Sibling lanes can run, wait, or block independently.
3. Completing or archiving a lane does not delete its concepts or evidence.
4. A merge creates a checkpoint and preserves every source node.
5. Concepts may appear in several lanes; the concept index keeps all references.
6. Tree state is advisory. It cannot manufacture execution authority or erase a
   physical boundary.
7. Future Branch ranking decides what to warm next; the chat tree records where
   that work lives and how it relates to the rest of the conversation.
8. A material objective change produces a topic split instead of contaminating the
   current node with unrelated context.
9. `running_verified` / `succeeded` are evidence-backed claims, never conversational
   assumptions.
10. Cross-talk occurs through durable state/events and provenance, not by pretending
    independent chats have direct awareness of one another.

The core tree implementation is
`Projects/Aurum/Experiments/chat_process_tree.py`. The read-only dashboard surface
loads `Projects/Aurum/chat-process-tree.json` and renders the concurrent frontier.
