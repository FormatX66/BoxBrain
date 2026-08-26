# Bluehost MCP adapter

`bluehost-index.php` is the production Streamable HTTP compatibility adapter for
the registered Aurum Chat Tree app at `https://aurum.arkmatx.com/chat-tree/mcp`.
It delegates every tree and shared-state operation to the canonical Python bridge
and passes explicit paths to state stored outside the web root.

The adapter exposes seven ChatGPT-facing actions:

- `show_chat_tree`
- `split_chat_topic`
- `publish_live_state`
- `read_live_state`
- `plan_chat_branch_consolidation`
- `consolidate_chat_branch`
- `dispatch_farmer_objective`

The Farmer action is a bounded actuator: ChatGPT can supply only an objective ID
and natural-language objective. The adapter owns the fixed GitHub repository,
event type, credential, continuation rules, and completion definition. Its token
is stored outside both the web root and versioned releases at
`/home1/madmorri/apps/aurum-chat-tree/secrets/github-token` with mode `0600`.

Deploy releases outside `public_html` under the versioned
`/home1/madmorri/apps/aurum-chat-tree/releases/` tree, point the `current` symlink
at the verified release, and install only the PHP adapter and `.htaccess` in the
existing `/chat-tree` web endpoint. Back up the previous adapter and release
pointer before promotion. Never copy the canonical event journal into a release;
it remains in `/home1/madmorri/apps/aurum-chat-tree/state/shared-state/`.
