# Aurum GUI v0.01

Aurum GUI is the local-first human interface for the Aurum system. The primary surface is the Aurum semantic/LLM interface, with verified machine state surrounding it.

## Design rules

- Chat/reasoning is the center of the interface.
- Machine state is read directly from the local system and Codelation state where available.
- The GUI talks to the Aurum-owned `AurumLLM` client contract rather than directly binding higher layers to a particular seed model.
- Model output is advisory. The GUI does not claim machine actions without independent evidence.
- The server binds to `127.0.0.1` by default. LAN exposure requires an explicit `--host 0.0.0.0` or `AURUM_GUI_HOST` setting.
- No third-party Python web framework is required for the bootstrap GUI.
- Familiarity comes before novelty: Aurum can begin with Aurum-native, Windows-like, macOS-like, or touch-oriented interaction patterns.
- Adaptation is gradual and reversible. Automatic learning must accumulate evidence before rearranging navigation, and the user can lock a profile or reset learned state at any time.
- Familiar profiles reproduce broad interaction conventions only; they are not pixel-for-pixel copies of another operating system.
- Interaction assistance is predictive, not coercive: Aurum may suggest the next click or complete likely text, but it does not silently execute a predicted action.

## Adaptive interface v0

`static/adaptive.js` maintains a small local preference state and chooses a familiarity profile in `Auto learn` mode from observed platform/touch evidence. Explicit profile selection locks the presentation until the user returns to automatic mode.

The first learned morph is deliberately conservative: after enough navigation use, Aurum reorders secondary lenses by demonstrated frequency while keeping `Overview` anchored. This is the initial mechanism for allowing the interface to change with the user without constantly moving controls.

The bootstrap preference state currently lives in browser-local storage (`aurum.ui.adaptation.v0`). The next persistence front is to promote verified preference evidence into Aurum semantic memory so the same user profile can follow the user across local Aurum nodes and displays.

## Interaction learning v0

`static/interaction.js` adds the first predictive interaction layer:

- **Click mapping:** semantic UI targets are recorded as bounded local tokens rather than screen coordinates. Repeated transitions build a simple click-path graph.
- **Intuitive next steps:** when a transition has enough repeated evidence, Aurum surfaces a `Likely next` hint. Selecting the hint highlights/focuses the predicted control; it does not activate it automatically.
- **Verbal prompts:** when the browser exposes the Web Speech Recognition API, a `Voice` control can fill the same prompt box used by typed input. The GUI remains fully usable when speech recognition is unavailable.
- **Contextual typing assistance:** the current GUI lens plus frequently reused prompts generate suggestions. The user can accept a completion with Tab or a click. Suggestions never submit themselves.
- **Prompt habit memory:** frequently reused prompts are ranked locally so Aurum can learn shorthand and preferred phrasing without requiring an LLM call for every keystroke.

Bootstrap interaction evidence lives in browser-local storage (`aurum.ui.interaction.v0`). This is intentionally temporary. The planned destination is Aurum semantic user memory, where click-path, typing, voice, and layout preference evidence can be correlated across devices while remaining inspectable/resettable by the user.

The long-term input path is modality-neutral:

`click / touch / keyboard / voice -> semantic intent -> verified capability`

That allows the same learned intent to be expressed through whichever input method is most natural in the current context.

## Run

```sh
python3 Projects/AurumGUI/server.py
```

Open `http://127.0.0.1:8765`.

If the Aurum LLM runtime is listening elsewhere:

```sh
AURUM_LLM_URL=http://127.0.0.1:8080 \
AURUM_LLM_MODEL=aurum-seed \
python3 Projects/AurumGUI/server.py
```

## API

- `GET /api/health` — GUI service readiness.
- `GET /api/status` — machine, Codelation, and local LLM status.
- `POST /api/chat` — bounded chat request through the Aurum-owned model interface.

## Near-term integration

1. Embed this service into the Aurum PC live image and start it with systemd.
2. Launch the interface automatically in a kiosk/fullscreen browser for local display while keeping the same HTTP surface for remote LAN access.
3. Feed adaptive-kernel machine contracts and generated device capability state into `/api/status`.
4. Add verified tool/event cards to the conversation instead of representing actions as plain model text.
5. Promote adaptive GUI and interaction evidence from browser-local state into Aurum semantic user memory.
6. Let capability-driven surfaces appear, merge, resize, and disappear according to current task and learned user behavior.
7. Add local speech-to-text and text-to-speech backends so voice remains available without depending on browser/cloud speech services.
