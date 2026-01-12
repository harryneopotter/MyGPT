# Logical, Low-Friction AI Chat System

This repository implements the system described in `final_prd_logical_low_friction_ai_chat_system.md`.

## Quick Start (Windows 11)

### Start Backend + UI Together
```powershell
pwsh -File .\scripts\start-dev.ps1
```
By default, this enables prompt/response logging to `data\llm_logs\`.
```powershell
pwsh -File .\scripts\start-dev.ps1 -DisableLlmLogging
```

### Backend (Control Plane)
```powershell
python -m pip install -r src\backend\requirements.txt
python -m uvicorn src.backend.app:app --reload --host 127.0.0.1 --port 8000
```

Health check (once running):
```powershell
curl http://127.0.0.1:8000/health
```

### UI (Tauri + React)
```powershell
cd src\ui
npm install
npm run tauri dev
```

The UI expects the backend at `http://127.0.0.1:8000` (override with `VITE_BACKEND_URL`).

## Project Layout
- `src/backend/`: FastAPI control plane + SQLite persistence
- `src/ui/`: Tauri + React/TypeScript UI
- `docs/`: guardrails, deviation policy, implementation plan
