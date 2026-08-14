# Aurum GUI v0.01

Aurum GUI is the local-first human interface for the Aurum system. It is deliberately not a conventional desktop shell yet: the primary surface is the Aurum semantic/LLM interface, with verified machine state surrounding it.

## Design rules

- Chat/reasoning is the center of the interface.
- Machine state is read directly from the local system and Codelation state where available.
- The GUI talks to the Aurum-owned `AurumLLM` client contract rather than directly binding higher layers to a particular seed model.
- Model output is advisory. The GUI does not claim machine actions without independent evidence.
- The server binds to `127.0.0.1` by default. LAN exposure requires an explicit `--host 0.0.0.0` or `AURUM_GUI_HOST` setting.
- No third-party Python web framework is required for the bootstrap GUI.

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
5. Replace fixed navigation lenses with capability-driven views generated from current Aurum state.
