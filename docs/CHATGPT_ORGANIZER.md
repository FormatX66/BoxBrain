# ChatGPT Chat Organizer

## Purpose

The organizer gives BoxBrain a durable, local index of ChatGPT chat metadata. It
preserves existing ChatGPT project membership, proposes a project for loose
chats, and keeps ambiguous titles in `00 Inbox & Ideas`.

It is intentionally read-only with respect to ChatGPT. BoxBrain does not scrape
browser storage, delete chats, create ChatGPT projects, or move conversations.
Suggested moves are shown in the dashboard for the operator to review and apply
through ChatGPT's supported **Move to project** action.

## Supported sources

- `chatgpt_app_index`: a metadata snapshot supplied by the signed-in desktop
  app. The snapshot contains IDs, titles, project membership, pin order, and
  update times. It does not contain message bodies.
- `chatgpt_data_export`: the same normalized schema populated from an operator's
  official ChatGPT data export. This source can be extended later to index
  exported conversation content after an explicit local import.

BoxBrain does not assume a public consumer ChatGPT conversation-management API.

## Organizer behavior

1. Existing ChatGPT project membership wins and is assigned high confidence.
2. Loose chats are classified by deterministic, inspectable title rules.
3. Uncertain chats remain in `00 Inbox & Ideas` with low confidence.
4. Repeated snapshots update records by stable external ID instead of creating
   duplicates.
5. Each import is append-only history with created, updated, unchanged,
   unassigned, and suggested-move counts.
6. Chats missing from a later partial snapshot are retained; partial visibility
   cannot silently remove local records.

The initial local buckets are:

- 00 Inbox & Ideas
- 10 BoxBrain & Automation
- 20 Web Production
- 21 Wet Beard Production
- 30 Creative Production
- 40 Operations & Accounts

Existing ChatGPT projects are also included in the project map, including empty
projects that have no chat in the visible snapshot.

## API

All routes use the existing local `X-BoxBrain-Token` authentication.

- `POST /api/v1/chat-organizer/import`
- `GET /api/v1/chat-organizer`
- `GET /api/v1/chat-organizer/chats`
- `GET /api/v1/chat-organizer/imports`

`POST /api/v1/chat-organizer/import` accepts a normalized snapshot:

```json
{
  "source": "chatgpt_app_index",
  "captured_at": "2026-07-28T04:48:04Z",
  "projects": [
    {"external_id": "project-id", "label": "Project name"}
  ],
  "chats": [
    {
      "external_id": "chat-id",
      "title": "Chat title",
      "updated_at": "2026-07-28T04:00:00Z",
      "project_external_id": null,
      "pinned_index": null
    }
  ]
}
```

The dashboard response includes totals, the complete project map, the latest
sync time, and recent chats with their classification reason and confidence.

## Current limitation

The desktop app exposes a bounded recent-chat index plus all pinned chats. The
organizer records exactly what the source exposes and reports that scope. For a
full historical corpus, request the official ChatGPT data export and normalize
its conversation files into the import schema.
