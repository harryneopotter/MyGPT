# Performance & Packaging Notes (Phase 7)
Capture measurements and packaging decisions here. Keep this file updated as evidence for Phase 7 gate checks.

## Performance Measurements
Record measurements on your primary dev machine.

## Phase 7 Evidence (Current)
- App startup target (<2s, no model warmup): FAIL (UI startup 5133.3 ms)
- Backend startup target (<2s): PASS (174 ms)
- UI idle CPU/memory: PASS (CPU near zero after 60s idle)
- Backend idle CPU/memory/events: PASS (CPU delta 0s; working set 0 MB; events delta 0)
- Time-to-first-token (TTFT): 2270.7 ms
- No-background-agents proof: PARTIAL (backend idle CPU delta 0s; network + events delta TBD)

## Local Model Server (llama.cpp)
Reference script: `F:\work\vsoa1\soa\scripts\start_llama_server.ps1`
- Binary: `F:\Users\Neo\AppData\Roaming\Jan\data\engines\llama.cpp\win-vulkan-x64\b5857\llama-server.exe`
- Model: `D:\local\mradermacher\Nemotron-Orchestrator-8B-Claude-4.5-Opus-Distill-i1-GGUF\Nemotron-Orchestrator-8B-Claude-4.5-Opus-Distill.i1-Q4_K_S.gguf`
- Host/Port: `127.0.0.1:8081` (OpenAI-compatible API)
- Args: `--ctx-size 4096 --threads 8 --parallel 2 --cont-batching`

### Backend
- Startup time (cold): 174 ms (local script: `scripts/measure-backend-startup.ps1`)
- Startup time (warm): TBD
- Idle CPU/memory (steady state): CPU delta 0s over 60s (script). Working set: measure manually (script could not read).
- Time-to-first-token (local model): 2270.7 ms (script: `scripts/measure-ttft.ps1`)

**Suggested measurement commands (Windows, PowerShell)**
- Backend cold start + health ready:
  - Start in one terminal: `python -m uvicorn src.backend.app:app --host 127.0.0.1 --port 8000`
  - In another: `Measure-Command { Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/health }`
- Automated log capture:
  - `pwsh -File .\scripts\measure-backend-startup.ps1`
  - Logs: `data\perf\backend_startup.stdout.log`, `data\perf\backend_startup.stderr.log`
- Idle CPU/memory:
  - Task Manager → Details → `python.exe` (record CPU + Memory after 60s idle).
- Time-to-first-token (local model):
  - Send a short `/chat` request and capture first token timestamp in UI or via a script.

### UI
- UI startup time: 5133.3 ms (script: `scripts/measure-ui-startup.ps1`)
- Idle CPU/memory (steady state): TBD

**Suggested measurement commands (Windows, PowerShell)**
- UI startup: `npm run tauri dev` and measure time until window is interactive.
- Assisted UI startup timing:
  - `pwsh -File .\scripts\measure-ui-startup.ps1`
- Idle CPU/memory:
  - Task Manager → Details → `Logical Low-Friction AI Chat` process (record CPU + Memory after 60s idle).

## Packaging Plan (Tauri)
- Backend packaging approach: package backend as a sidecar executable (PyInstaller) and bundle it with the Tauri app.
- How the backend is started by the UI: Tauri launches the sidecar on startup and shuts it down on exit.
- Offline behavior verified: must pass with network disabled; model URL points to local llama.cpp only.

## No-Background-Agents Proof
- With app idle, CPU near zero: backend CPU delta 0s over 60s (script).
- No periodic network calls: PASS (manual check in Resource Monitor).
- No background tool execution: backend `events` delta 0 over 60s (script).

**Suggested verification steps**
- With app idle (no active chat), confirm CPU is near zero for 60s.
- Use Resource Monitor to verify no periodic network calls.
- Check `events` table: no new `tool_run` or LLM request entries without a user message.

## Verification Commands (Fill In)
- App startup target (<2s, no model warmup): FAIL (UI startup 5133.3 ms)
- Backend startup: `pwsh -File .\scripts\measure-backend-startup.ps1`
- UI startup: `pwsh -File .\scripts\measure-ui-startup.ps1`
- TTFT: `pwsh -File .\scripts\measure-ttft.ps1 -Prompt "Hello"`
  - Ensure backend is started with `MYGPT_MODEL_URL=http://127.0.0.1:8081`
- Backend idle CPU/memory/events: `pwsh -File .\scripts\measure-backend-idle.ps1`
- UI idle CPU/memory: measure in Task Manager after 60s idle
