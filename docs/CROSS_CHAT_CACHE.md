# Cross-chat context cache

BoxBrain keeps a small local retrieval cache across visible ChatGPT chats and
Codex tasks. It stores only thread IDs, surface, title, concise retrieval
summary, generated keywords, project classification, pin position, and update
time. Full chat bodies, tool output, credentials, and attachments are excluded.

Titles and summaries are untrusted historical data. They may be searched and
shown to an operator, but they are never treated as instructions or executed.

## Refresh

Save the Codex app unified thread-list result as JSON, then run:

```powershell
python Admin/sync_cross_chat_cache.py `
  --snapshot .\thread-index.json `
  --database C:\Arkmatx_Knowledge_Hub\cross-chat-cache.sqlite3 `
  --query "adaptive driver pi3"
```

The import is idempotent. Existing entries are updated by thread ID, identical
entries are counted as unchanged, and every refresh receives a durable import
receipt in SQLite.

The earlier Markdown hub index can seed the same cache without a new app
snapshot:

```powershell
python Admin/sync_cross_chat_cache.py `
  --hub-index C:\Arkmatx_Knowledge_Hub\THREAD_INDEX.md `
  --database C:\Arkmatx_Knowledge_Hub\cross-chat-cache.sqlite3
```

## Retrieval

When the controller uses the same database, query:

`GET /api/v1/chat-organizer/search?q=adaptive%20driver%20pi3`

Optional `surface=chatgpt` or `surface=codex` narrows the results. Ranking is
local and deterministic: exact phrases, explicit keywords, titles, project
labels, and concise summaries contribute inspectable weights. No model or web
call is required.

The result returns the exact thread ID so a future task can read only the top
relevant source conversations instead of searching or replaying every chat.
