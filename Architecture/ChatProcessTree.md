# Chat Process Tree

Human chat is usually linear because a person needs one readable focus at a time.
Machine work is not linear. Aurum therefore keeps a durable process tree behind
the focused conversation instead of discarding every branch that is not currently
being discussed.

## Model

```text
conversation root
  ├─ process lane: Hopper reachability
  │    ├─ evidence / blocker / recovery checkpoints
  │    └─ pinned concepts
  ├─ process lane: adaptive kernel
  │    ├─ repository and CI work
  │    └─ physical promotion boundary
  └─ process lane: chat-tree implementation
       └─ merge checkpoint linking relevant prior lanes
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

The experimental implementation is
`Projects/Aurum/Experiments/chat_process_tree.py`. The read-only dashboard surface
loads `Projects/Aurum/chat-process-tree.json` and renders the concurrent frontier.
