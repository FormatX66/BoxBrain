# TypeTrix Windows Architecture

## Principle

**Help the user now; help the user grow next.**

TypeTrix treats editing behavior as evidence of friction, not evidence of deficiency. The system should first preserve the user's intent, then optionally use repeated patterns to teach in ways the user has chosen.

## Event model

The core consumes a small stream of interaction events instead of a permanent transcript:

- character/input activity
- backspace/delete
- token snapshot (ephemeral, when permitted)
- cursor/navigation changes
- pauses
- suggestion shown / accepted / rejected / undone
- application/surface policy state

The Windows adapter is responsible for refusing protected/password contexts and for minimizing data sent into the core.

## Friction signals

Examples of evidence that can raise a word-search/friction confidence score:

- several backspaces in a short window
- repeated type -> erase -> retype cycles around the same token
- multiple distinct partial-word attempts
- a long pause immediately after repeated edits
- phonetic or near-keyboard attempts that converge on one likely concept
- a suggested word being accepted and then immediately deleted

No single signal should be treated as proof.

## Confidence ladder

- `< 0.45`: do nothing
- `0.45–0.69`: prepare candidates, do not interrupt
- `0.70–0.89`: show a small ghost/candidate surface
- `>= 0.90`: allow a user-configurable fast correction path, always undoable

Thresholds are initial defaults and should become user-adaptive.

## Two learning loops

### Assistance loop

Goal: reduce immediate friction.

`events -> context -> intent candidates -> confidence -> suggestion/correction -> feedback`

### Teaching loop

Goal: reduce future assistance need.

`recurring pattern -> user-approved coaching opportunity -> tiny exercise/explanation -> improvement measurement`

Teaching is optional. Assistance must not be withheld to force a lesson.

## Personal model

Durable state should prefer compact derived features over raw text:

- repeated confusion pairs
- common transpositions
- frequently searched-for words explicitly retained by the user
- correction acceptance/rejection rates
- timing/backspace pattern baselines
- preferred vocabulary/register
- coaching preferences

The model belongs to the user. Export/delete/reset should be first-class operations.

## Windows path

Use Microsoft Text Services Framework (TSF) as the primary integration layer. A TSF text service is a COM in-process server registered with TSF. The adapter can register an `ITfKeyEventSink` through `ITfKeystrokeMgr` and use TSF composition/candidate mechanisms where appropriate.

We avoid a global low-level keyboard hook as the architectural default because TypeTrix should integrate as a text service and should not indiscriminately capture system keystrokes.

## Capability boundary

The Windows plugin is a compatibility phenotype of the broader capability. The core logic must stay portable so that the same behavior can later be expressed natively by Aurum as `TR8:INTENT` / a user-named Trix.
