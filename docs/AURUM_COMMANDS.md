# Aurum Command Registry

This file is the canonical list of Aurum / BoxBrain commands that are actually implemented or explicitly documented.

## Rule

A command is not considered real merely because it sounds reasonable, appears in a plan, or was suggested in chat. It must have repository evidence showing where it is implemented or documented.

Each command should move through these states:

1. **Proposed** — desired vocabulary only; do not tell a user to run it.
2. **Implemented** — executable handling exists in code.
3. **Tested** — automated or bounded functional proof exists.
4. **Physical** — successfully exercised on an authorized physical Aurum node such as Hopper.

Voice/chat assistants should consult this file before giving Bruce an Aurum command. If a command is absent or still Proposed, do not invent it.

## Verified / documented commands

| Command | Scope | State | Evidence / behavior | Hopper-safe? |
|---|---|---:|---|---|
| `RUN` | BoxBrain approval-gated AI diagnostics | Documented | After reviewing a typed diagnostic proposal, `RUN` authorizes one of the fixed read-only diagnostics selected by the model. User text does not become shell input. | Not a general Hopper maintenance command |
| `RESET` | BoxBrain dashboard emergency-stop reset | Documented | Required confirmation phrase to reset the persisted emergency-stop state from the dashboard. | Dashboard control, not Hopper shell/GUI maintenance |
| `OPEN` | BoxBrain target/session manager | Documented | Required confirmation phrase before launching an operator-controlled OS session to an enrolled target. | Session-launch control, not Hopper update command |

## Hopper / Aurum-native maintenance vocabulary

The following are desirable stable Aurum-facing commands, but they are **not yet verified as implemented**. Do not instruct Bruce to run them until their state advances.

| Proposed command | Intended meaning | State |
|---|---|---:|
| `aurum status` | Show node identity, generation, runtime/seed revision, GUI revision, and health | Proposed |
| `aurum reconcile` | Reconcile the node with its trusted current Aurum state without requiring manual Git administration | Proposed |
| `aurum update` | Apply an approved newer Aurum runtime/seed state through the Aurum-native update path | Proposed |
| `aurum gui reload` | Reload/restart only the human-facing GUI after a verified local update | Proposed |
| `aurum diagnose` | Run safe Aurum diagnostics and report failures in Aurum terms | Proposed |
| `aurum recover` | Enter or invoke the bounded known-good/rollback recovery path | Proposed |

## Logging requirements

When a command becomes real, record:

- exact command text and aliases;
- parser/handler implementation path;
- permission or confirmation requirements;
- side effects and safety boundary;
- automated test path and result;
- first physical node proof;
- first Hopper proof, when applicable;
- version/generation first supporting it;
- deprecated replacements, if any.

## Assistant behavior

Before suggesting an Aurum command:

1. Read this registry.
2. Use only commands whose documented scope matches the requested action.
3. Never substitute Linux, Windows, Git, or shell administration for an Aurum-native command unless Bruce explicitly asks for the underlying bootstrap procedure.
4. If no real Aurum command exists for the task, say so and treat that missing command/path as an implementation gap.

Last initialized: 2026-08-21.
