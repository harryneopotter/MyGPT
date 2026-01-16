from __future__ import annotations

import json
import os
import sqlite3
import uuid
import hashlib
import logging
from logging.handlers import RotatingFileHandler
import time
from pathlib import Path
from typing import AsyncIterator, Literal

import asyncio
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from contextlib import asynccontextmanager

from .model_gateway import build_prompt as model_build_prompt
from .model_gateway import generate as model_generate
from .response_policy import evaluate_clarifying_question
from .tools import build_tool_context, get_tool_definitions, run_tool

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.getenv("MYGPT_DATA_DIR", str(REPO_ROOT / "data")))
DB_PATH = Path(os.getenv("MYGPT_DB_PATH", str(DATA_DIR / "chat.db")))
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"
@asynccontextmanager
async def lifespan(_: FastAPI):
    _log_startup_marker("backend_startup")
    logger.info("backend_startup timestamp logged")
    yield


app = FastAPI(title="Logical Low-Friction AI Chat Backend", lifespan=lifespan)
logger = logging.getLogger("mygpt")


def _log_dir() -> Path:
    return Path(os.getenv("MYGPT_LOG_DIR", str(DATA_DIR / "logs")))


def _setup_logging() -> None:
    log_dir = _log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    level_name = os.getenv("MYGPT_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logger.setLevel(level)

    formatter = logging.Formatter(
        "%(asctime)s\t%(levelname)s\t%(name)s\t%(message)s"
    )

    def _has_handler(path: Path) -> bool:
        for handler in logger.handlers:
            if isinstance(handler, RotatingFileHandler) and handler.baseFilename == str(path):
                return True
        return False

    app_log = log_dir / "app.log"
    err_log = log_dir / "error.log"
    if not _has_handler(app_log):
        handler = RotatingFileHandler(app_log, maxBytes=5_000_000, backupCount=5)
        handler.setLevel(level)
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    if not _has_handler(err_log):
        err_handler = RotatingFileHandler(err_log, maxBytes=5_000_000, backupCount=5)
        err_handler.setLevel(logging.ERROR)
        err_handler.setFormatter(formatter)
        logger.addHandler(err_handler)


_setup_logging()

cors_origins = [
    origin.strip()
    for origin in os.getenv("MYGPT_CORS_ORIGINS", "http://localhost:1420").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("request_failed method=%s path=%s", request.method, request.url.path)
        raise
    duration_ms = round((time.time() - start) * 1000, 2)
    logger.info(
        "request_complete method=%s path=%s status=%s duration_ms=%s",
        request.method,
        request.url.path,
        getattr(response, "status_code", "unknown"),
        duration_ms,
    )
    return response



def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _llm_logging_enabled() -> bool:
    return os.getenv("MYGPT_LOG_LLM", "0").strip() == "1"


def _startup_log_path() -> Path:
    return Path(
        os.getenv("MYGPT_STARTUP_LOG", str(DATA_DIR / "perf" / "backend_startup.log"))
    )


def _log_startup_marker(event: str) -> None:
    path = _startup_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{timestamp}\t{event}\n")


CURRENT_MODEL_URL = os.getenv("MYGPT_MODEL_URL", "http://127.0.0.1:8080")


def _get_model_url() -> str:
    return CURRENT_MODEL_URL


def _set_model_url(value: str) -> None:
    global CURRENT_MODEL_URL
    CURRENT_MODEL_URL = value.strip()


MODEL_SWITCH_CONFIG = REPO_ROOT / "model-switch" / "models.json"


def _load_model_options() -> dict:
    if not MODEL_SWITCH_CONFIG.exists():
        return {"models": [], "model_url": _get_model_url()}
    try:
        return json.loads(MODEL_SWITCH_CONFIG.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"models": [], "model_url": _get_model_url()}


def _read_tail(path: Path, limit: int) -> list[str]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        lines = handle.readlines()
    return [line.rstrip("\n") for line in lines[-limit:]]


def _llm_log_dir() -> Path:
    return Path(os.getenv("MYGPT_LLM_LOG_DIR", str(DATA_DIR / "llm_logs")))


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _strip_ansi(text: str) -> str:
    import re

    return re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", text)


def _strip_think_blocks(text: str) -> str:
    wrappers = [
        ("<think>", "</think>"),
        ("〈thinking〉", "〈/thinking〉"),
        ("＜thinking＞", "＜/thinking＞"),
    ]

    for _, close in wrappers:
        idx = text.rfind(close)
        if idx != -1:
            return text[idx + len(close) :]

    cleaned = text
    for open_tag, _ in wrappers:
        cleaned = cleaned.replace(open_tag, "")
    return cleaned


def _truncate_at_role_markers(text: str) -> str:
    import re

    cleaned = text.strip()
    cleaned = re.sub(r"^\s*Assistant:\s*", "", cleaned)
    match = re.search(r"(?m)^(User:|System:|Assistant:)\s*", cleaned)
    if match and match.start() > 0:
        return cleaned[: match.start()].rstrip()
    return cleaned


def init_db() -> None:
    conn = _connect()
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))

    row = conn.execute("SELECT id FROM conversations ORDER BY id LIMIT 1").fetchone()
    if row is None:
        cursor = conn.execute(
            "INSERT INTO conversations (title) VALUES (?)", ("Legacy",)
        )
        conversation_id = int(cursor.lastrowid)
        conn.execute(
            """
            INSERT OR IGNORE INTO conversation_messages (conversation_id, message_id)
            SELECT ?, id FROM messages
            """,
            (conversation_id,),
        )
    else:
        conversation_id = int(row["id"])
        conn.execute(
            """
            INSERT OR IGNORE INTO conversation_messages (conversation_id, message_id)
            SELECT ?, m.id
            FROM messages m
            LEFT JOIN conversation_messages cm ON cm.message_id = m.id
            WHERE cm.message_id IS NULL
            """,
            (conversation_id,),
        )

    conn.commit()
    conn.close()


init_db()


class ConversationCreate(BaseModel):
    title: str | None = None


class MessageCreate(BaseModel):
    content: str = Field(min_length=1)
    role: Literal["user", "assistant"]
    corrects_message_id: int | None = None
    conversation_id: int | None = None


class ChatRequest(BaseModel):
    content: str = Field(min_length=1)
    conversation_id: int | None = None


class RegenerateRequest(BaseModel):
    target_message_id: int
    conversation_id: int | None = None


class ToolRunRequest(BaseModel):
    tool_id: str
    tool_input: dict = Field(default_factory=dict)
    conversation_id: int | None = None
    causality_message_id: int | None = None
    confirmed: bool = False


class PreferenceProposalRow(BaseModel):
    id: int
    conversation_id: int
    key: str
    value: str
    proposal_text: str
    rationale: str | None = None
    status: Literal["pending", "approved", "rejected", "dismissed"]
    created_at: str
    decided_at: str | None = None
    causality_message_id: int | None = None
    assistant_message_id: int | None = None


class ModelConfigRequest(BaseModel):
    model_url: str = Field(min_length=1)


class ModelSwitchRequest(BaseModel):
    model_key: str = Field(min_length=1)
    confirmed: bool = False


class ServiceActionRequest(BaseModel):
    confirmed: bool = False
    model_key: str | None = None


def _load_active_preferences(
    conn: sqlite3.Connection, scope: str = "global"
) -> dict[str, str]:
    reset_row = conn.execute(
        "SELECT created_at FROM preference_resets WHERE scope = ? ORDER BY id DESC LIMIT 1",
        (scope,),
    ).fetchone()
    reset_created_at: str | None = None
    if reset_row is not None:
        reset_created_at = str(reset_row["created_at"])

    if reset_created_at is None:
        rows = conn.execute(
            "SELECT key, value FROM preferences WHERE scope = ? ORDER BY id",
            (scope,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT key, value
            FROM preferences
            WHERE scope = ? AND created_at > ?
            ORDER BY id
            """,
            (scope, reset_created_at),
        ).fetchall()
    prefs: dict[str, str] = {}
    for r in rows:
        prefs[str(r["key"])] = str(r["value"])
    return prefs


def _infer_preference_proposal(
    history: list[dict], approved_preferences: dict[str, str]
) -> dict[str, str] | None:
    user_texts = [str(m.get("content", "")) for m in history if m.get("role") == "user"]
    window = [t.lower() for t in user_texts[-6:]]
    if not window:
        return None

    candidates: list[tuple[str, str, tuple[str, ...]]] = [
        ("verbosity", "concise", ("concise", "brief", "short", "terse")),
        ("verbosity", "detailed", ("detailed", "detail", "thorough", "full")),
        ("format", "bullets", ("bullet", "bullets", "bullet points")),
    ]

    best: tuple[int, str, str] | None = None
    for key, value, terms in candidates:
        count = 0
        for t in window:
            if any(term in t for term in terms):
                count += 1
        if count < 2:
            continue
        if best is None or count > best[0]:
            best = (count, key, value)

    if best is None:
        return None

    _, key, value = best
    if approved_preferences.get(key) == value:
        return None

    proposal_text = {
        ("verbosity", "concise"): "Prefer concise answers by default.",
        ("verbosity", "detailed"): "Prefer detailed answers by default.",
        ("format", "bullets"): "Prefer bullet lists when possible.",
    }.get((key, value), f"Set {key}={value} as a default.")

    rationale = "This shows up repeatedly in recent messages; store it as a default?"
    return {
        "key": key,
        "value": value,
        "proposal_text": proposal_text,
        "rationale": rationale,
    }


def _get_pending_proposal(
    conn: sqlite3.Connection, conversation_id: int
) -> dict | None:
    row = conn.execute(
        """
        SELECT
          id, conversation_id, key, value, proposal_text, rationale,
          status, created_at, decided_at, causality_message_id, assistant_message_id
        FROM preference_proposals
        WHERE conversation_id = ? AND status = 'pending'
        ORDER BY id DESC
        LIMIT 1
        """,
        (conversation_id,),
    ).fetchone()
    return dict(row) if row else None


def _insert_event(
    conn: sqlite3.Connection,
    *,
    event_type: str,
    payload: dict,
    conversation_id: int | None = None,
    causality_message_id: int | None = None,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO events (type, payload_json, conversation_id, causality_message_id)
        VALUES (?, ?, ?, ?)
        """,
        (
            event_type,
            json.dumps(payload, ensure_ascii=False),
            conversation_id,
            causality_message_id,
        ),
    )
    return int(cursor.lastrowid)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/model")
async def get_model() -> dict[str, str]:
    return {"model_url": _get_model_url()}


@app.post("/model")
async def set_model(body: ModelConfigRequest) -> dict[str, str]:
    model_url = body.model_url.strip()
    if not model_url:
        raise HTTPException(status_code=400, detail="model_url is required")
    _set_model_url(model_url)
    conn = _connect()
    try:
        _insert_event(
            conn,
            event_type="model_switch",
            payload={"model_url": model_url},
            conversation_id=None,
            causality_message_id=None,
        )
        conn.commit()
    finally:
        conn.close()
    return {"model_url": _get_model_url()}


@app.get("/model/options")
async def get_model_options() -> dict:
    return _load_model_options()


@app.post("/model/switch")
async def switch_model(body: ModelSwitchRequest) -> dict:
    if not body.confirmed:
        raise HTTPException(status_code=400, detail="Model switch requires confirmation")

    options = _load_model_options()
    models = options.get("models", [])
    match = next((m for m in models if m.get("key") == body.model_key), None)
    if match is None:
        raise HTTPException(status_code=404, detail="Unknown model key")

    model_path = str(match.get("gguf_path", "")).strip()
    if not model_path:
        raise HTTPException(status_code=400, detail="Model path is missing")

    script_path = REPO_ROOT / "model-switch" / "model_switcher.ps1"
    if not script_path.exists():
        raise HTTPException(status_code=500, detail="model_switcher.ps1 not found")

    env = os.environ.copy()
    env.setdefault("LLAMA_SERVER", os.getenv("MYGPT_LLAMA_SERVER", ""))
    env.setdefault("LLAMA_PORT", os.getenv("MYGPT_LLAMA_PORT", "8081"))
    env.setdefault("LLAMA_CTX_SIZE", os.getenv("MYGPT_LLAMA_CTX_SIZE", "4096"))
    env.setdefault("LLAMA_THREADS", os.getenv("MYGPT_LLAMA_THREADS", "8"))
    env.setdefault("LLAMA_PARALLEL", os.getenv("MYGPT_LLAMA_PARALLEL", "2"))
    env.setdefault("LLAMA_CONT_BATCHING", os.getenv("MYGPT_LLAMA_CONT_BATCHING", "1"))
    env.setdefault("LLAMA_MAX_WAIT_SECONDS", os.getenv("MYGPT_LLAMA_MAX_WAIT_SECONDS", "120"))

    timeout = int(env.get("LLAMA_MAX_WAIT_SECONDS", "120")) + 30
    res = await _run_powershell_async(script_path, ["-Model", model_path], env, timeout)
    
    error = None
    if not res["success"]:
        error = res["stderr"] or res["stdout"] or "Switch failed"

    payload = {
        "model_key": body.model_key,
        "model_path": model_path,
        "stdout": res["stdout"],
        "stderr": res["stderr"],
        "success": res["success"],
    }

    conn = _connect()
    try:
        _insert_event(
            conn,
            event_type="model_switch",
            payload=payload,
            conversation_id=None,
            causality_message_id=None,
        )
        conn.commit()
    finally:
        conn.close()

    if error:
        raise HTTPException(status_code=500, detail=error)

    model_url = options.get("model_url") or _get_model_url()
    _set_model_url(model_url)
    return {"model_url": _get_model_url(), "model_key": body.model_key}


@app.get("/services/status")
async def service_status() -> dict:
    llama_url = _get_model_url().rstrip("/")
    status = {"backend": "ok", "llama": {"url": llama_url, "running": False}}
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{llama_url}/health")
            status["llama"]["running"] = resp.status_code == 200
    except Exception:
        status["llama"]["running"] = False
    return status


@app.get("/logs")
async def get_logs(
    limit: int = Query(default=200),
    level: str | None = Query(default=None),
    contains: str | None = Query(default=None),
) -> dict:
    safe_limit = max(1, min(limit, 2000))
    log_dir = _log_dir()

    def _filter(lines: list[str]) -> list[str]:
        filtered = lines
        if level:
            needle = f"\t{level.upper()}\t"
            filtered = [line for line in filtered if needle in line]
        if contains:
            filtered = [line for line in filtered if contains in line]
        return filtered[-safe_limit:]

    app_lines = _read_tail(log_dir / "app.log", 5000)
    err_lines = _read_tail(log_dir / "error.log", 5000)
    return {
        "app_log": _filter(app_lines),
        "error_log": _filter(err_lines),
    }


@app.get("/events")
async def list_events(
    limit: int = Query(default=200),
    event_type: str | None = Query(default=None),
    conversation_id: int | None = Query(default=None),
) -> dict:
    safe_limit = max(1, min(limit, 2000))
    conn = _connect()
    try:
        params = []
        clauses = []
        if event_type:
            clauses.append("type = ?")
            params.append(event_type)
        if conversation_id is not None:
            clauses.append("conversation_id = ?")
            params.append(conversation_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = conn.execute(
            f"""
            SELECT id, type, payload_json, created_at, conversation_id, causality_message_id
            FROM events
            {where}
            ORDER BY id DESC
            LIMIT ?
            """,
            (*params, safe_limit),
        ).fetchall()
        return {"events": [dict(r) for r in rows]}
    finally:
        conn.close()



async def _run_powershell_async(script_path: Path, args: list[str], env: dict | None, timeout: int) -> dict:
    cmd = ["pwsh", "-File", str(script_path)] + args
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        return {
            "returncode": process.returncode,
            "stdout": stdout.decode(errors="replace").strip(),
            "stderr": stderr.decode(errors="replace").strip(),
            "success": process.returncode == 0
        }
    except asyncio.TimeoutError:
        return {"returncode": -1, "stdout": "", "stderr": "Timeout", "success": False}
    except Exception as e:
        return {"returncode": -1, "stdout": "", "stderr": str(e), "success": False}

@app.post("/services/llama/start")
async def start_llama(body: ServiceActionRequest) -> dict:
    if not body.confirmed:
        raise HTTPException(status_code=400, detail="Confirmation required")
    options = _load_model_options()
    model_key = body.model_key or options.get("default_model_key")
    if not model_key:
        raise HTTPException(status_code=400, detail="model_key is required")
    models = options.get("models", [])
    match = next((m for m in models if m.get("key") == model_key), None)
    if match is None:
        raise HTTPException(status_code=404, detail="Unknown model key")
    model_path = str(match.get("gguf_path", "")).strip()
    if not model_path:
        raise HTTPException(status_code=400, detail="Model path is missing")

    script_path = REPO_ROOT / "model-switch" / "model_switcher.ps1"
    if not script_path.exists():
        raise HTTPException(status_code=500, detail="model_switcher.ps1 not found")

    env = os.environ.copy()
    env.setdefault("LLAMA_SERVER", os.getenv("MYGPT_LLAMA_SERVER", ""))
    env.setdefault("LLAMA_PORT", os.getenv("MYGPT_LLAMA_PORT", "8081"))
    env.setdefault("LLAMA_CTX_SIZE", os.getenv("MYGPT_LLAMA_CTX_SIZE", "4096"))
    env.setdefault("LLAMA_THREADS", os.getenv("MYGPT_LLAMA_THREADS", "8"))
    env.setdefault("LLAMA_PARALLEL", os.getenv("MYGPT_LLAMA_PARALLEL", "2"))
    env.setdefault("LLAMA_CONT_BATCHING", os.getenv("MYGPT_LLAMA_CONT_BATCHING", "1"))
    env.setdefault("LLAMA_MAX_WAIT_SECONDS", os.getenv("MYGPT_LLAMA_MAX_WAIT_SECONDS", "120"))

    timeout = int(env.get("LLAMA_MAX_WAIT_SECONDS", "120")) + 30
    res = await _run_powershell_async(script_path, ["-Model", model_path], env, timeout)
    
    error = None
    if not res["success"]:
        error = res["stderr"] or res["stdout"] or "Start failed"

    payload = {
        "action": "start",
        "model_key": model_key,
        "model_path": model_path,
        "stdout": res["stdout"],
        "stderr": res["stderr"],
        "success": res["success"],
    }
    conn = _connect()
    try:
        _insert_event(
            conn,
            event_type="service_start",
            payload=payload,
            conversation_id=None,
            causality_message_id=None,
        )
        conn.commit()
    finally:
        conn.close()

    if error:
        raise HTTPException(status_code=500, detail=error)
    model_url = options.get("model_url") or _get_model_url()
    _set_model_url(model_url)
    return {"status": "started", "model_url": _get_model_url(), "model_key": model_key}


@app.post("/services/llama/stop")
async def stop_llama(body: ServiceActionRequest) -> dict:
    if not body.confirmed:
        raise HTTPException(status_code=400, detail="Confirmation required")
    script_path = REPO_ROOT / "model-switch" / "stop_llama.ps1"
    if not script_path.exists():
        raise HTTPException(status_code=500, detail="stop_llama.ps1 not found")

    res = await _run_powershell_async(script_path, [], None, 30)
    
    error = None
    if not res["success"]:
        error = res["stderr"] or res["stdout"] or "Stop failed"

    payload = {
        "action": "stop",
        "stdout": res["stdout"],
        "stderr": res["stderr"],
        "success": res["success"],
    }
    conn = _connect()
    try:
        _insert_event(
            conn,
            event_type="service_stop",
            payload=payload,
            conversation_id=None,
            causality_message_id=None,
        )
        conn.commit()
    finally:
        conn.close()

    if error:
        raise HTTPException(status_code=500, detail=error)
    return {"status": "stopped"}


@app.get("/tools")
async def list_tools() -> dict[str, list[dict]]:
    tools = []
    for tool in get_tool_definitions():
        tools.append(
            {
                "tool_id": tool.tool_id,
                "description": tool.description,
                "input_schema": tool.input_schema,
                "output_schema": tool.output_schema,
                "requires_confirmation": tool.requires_confirmation,
                "requires_network": tool.requires_network,
            }
        )
    return {"tools": tools}


@app.post("/tools/run")
async def run_tool_endpoint(req: ToolRunRequest) -> dict:
    if req.causality_message_id is None:
        raise HTTPException(status_code=400, detail="causality_message_id is required")

    conn = _connect()
    try:
        conversation_id = req.conversation_id
        if conversation_id is None:
            conversation_id = _get_conversation_id_for_message(
                conn, req.causality_message_id
            )

        ctx = build_tool_context(REPO_ROOT, DB_PATH)
        started_at = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
        start = time.time()
        success = True
        output: dict | None = None
        error: str | None = None
        try:
            output = await run_tool(req.tool_id, req.tool_input, ctx, confirmed=req.confirmed)
        except Exception as exc:
            success = False
            error = str(exc)

        duration = time.time() - start
        ended_at = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
        payload = {
            "tool_id": req.tool_id,
            "input": req.tool_input,
            "output": output,
            "error": error,
            "confirmed": req.confirmed,
            "started_at": started_at,
            "ended_at": ended_at,
            "duration_sec": round(duration, 4),
            "success": success,
        }
        _insert_event(
            conn,
            event_type="tool_run",
            payload=payload,
            conversation_id=conversation_id,
            causality_message_id=req.causality_message_id,
        )
        conn.commit()
    finally:
        conn.close()

    return {"success": success, "output": output, "error": error}


def _get_latest_conversation_id(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT id FROM conversations ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if row is None:
        cursor = conn.execute(
            "INSERT INTO conversations (title) VALUES (?)", ("Legacy",)
        )
        return int(cursor.lastrowid)
    return int(row["id"])


def _get_conversation_id_for_message(
    conn: sqlite3.Connection, message_id: int
) -> int | None:
    row = conn.execute(
        """
        SELECT conversation_id
        FROM conversation_messages
        WHERE message_id = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (message_id,),
    ).fetchone()
    if row is None:
        return None
    return int(row["conversation_id"])


def _ensure_conversation(conn: sqlite3.Connection, conversation_id: int) -> None:
    row = conn.execute(
        "SELECT 1 FROM conversations WHERE id = ?", (conversation_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Conversation not found")


@app.get("/conversations")
async def list_conversations() -> list[dict]:
    conn = _connect()
    rows = conn.execute(
        """
        SELECT
          c.id,
          c.title,
          c.created_at,
          COUNT(cm.message_id) AS message_count
        FROM conversations c
        LEFT JOIN conversation_messages cm ON cm.conversation_id = c.id
        GROUP BY c.id
        ORDER BY c.id DESC
        """
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/conversations")
async def create_conversation(body: ConversationCreate) -> dict[str, int]:
    conn = _connect()
    try:
        cursor = conn.execute(
            "INSERT INTO conversations (title) VALUES (?)", (body.title,)
        )
        conn.commit()
        return {"id": int(cursor.lastrowid)}
    finally:
        conn.close()


@app.get("/messages")
async def list_messages(
    conversation_id: int | None = Query(default=None),
) -> list[dict]:
    conn = _connect()
    try:
        if conversation_id is None:
            conversation_id = _get_latest_conversation_id(conn)
        else:
            _ensure_conversation(conn, conversation_id)

        rows = conn.execute(
            """
            SELECT m.id, m.content, m.role, m.timestamp, m.corrects_message_id
            FROM messages m
            JOIN conversation_messages cm ON cm.message_id = m.id
            WHERE cm.conversation_id = ?
            ORDER BY m.id
            """,
            (conversation_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@app.get("/preferences")
async def list_preferences(scope: str = Query(default="global")) -> dict:
    conn = _connect()
    try:
        reset_row = conn.execute(
            "SELECT id, created_at, reset_event_id FROM preference_resets WHERE scope = ? ORDER BY id DESC LIMIT 1",
            (scope,),
        ).fetchone()
        reset = dict(reset_row) if reset_row else None

        rows = conn.execute(
            """
            SELECT id, key, value, scope, created_at, approved_event_id, source_proposal_id
            FROM preferences
            WHERE scope = ?
            ORDER BY id
            """,
            (scope,),
        ).fetchall()
        return {"scope": scope, "reset": reset, "preferences": [dict(r) for r in rows]}
    finally:
        conn.close()


@app.post("/preferences/reset")
async def reset_preferences(
    scope: str = Query(default="global"),
    conversation_id: int | None = Query(default=None),
    causality_message_id: int | None = Query(default=None),
) -> dict:
    conn = _connect()
    try:
        event_id = _insert_event(
            conn,
            event_type="preferences_reset",
            payload={"actor": "user", "scope": scope},
            conversation_id=conversation_id,
            causality_message_id=causality_message_id,
        )
        cursor = conn.execute(
            "INSERT INTO preference_resets (scope, reset_event_id) VALUES (?, ?)",
            (scope, event_id),
        )
        conn.commit()
        return {"reset_id": int(cursor.lastrowid), "event_id": event_id}
    finally:
        conn.close()


@app.get("/preference-proposals")
async def list_preference_proposals(
    conversation_id: int | None = Query(default=None),
    status: str = Query(default="pending"),
) -> dict:
    conn = _connect()
    try:
        if conversation_id is None:
            conversation_id = _get_latest_conversation_id(conn)
        else:
            _ensure_conversation(conn, conversation_id)

        rows = conn.execute(
            """
            SELECT
              id, conversation_id, key, value, proposal_text, rationale,
              status, created_at, decided_at, causality_message_id, assistant_message_id
            FROM preference_proposals
            WHERE conversation_id = ? AND status = ?
            ORDER BY id DESC
            """,
            (conversation_id, status),
        ).fetchall()
        return {"proposals": [dict(r) for r in rows]}
    finally:
        conn.close()


@app.post("/preference-proposals/{proposal_id}/approve")
async def approve_preference_proposal(proposal_id: int) -> dict:
    conn = _connect()
    try:
        row = conn.execute(
            """
            SELECT id, conversation_id, key, value, status, causality_message_id
            FROM preference_proposals
            WHERE id = ?
            """,
            (proposal_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Proposal not found")
        if row["status"] != "pending":
            raise HTTPException(status_code=409, detail="Proposal is not pending")

        payload = {
            "actor": "user",
            "proposal_id": int(row["id"]),
            "key": str(row["key"]),
            "value": str(row["value"]),
        }
        event_id = _insert_event(
            conn,
            event_type="preference_approved",
            payload=payload,
            conversation_id=int(row["conversation_id"]),
            causality_message_id=row["causality_message_id"],
        )
        cursor = conn.execute(
            """
            INSERT INTO preferences (key, value, scope, approved_event_id, source_proposal_id)
            VALUES (?, ?, 'global', ?, ?)
            """,
            (row["key"], row["value"], event_id, int(row["id"])),
        )
        conn.execute(
            """
            UPDATE preference_proposals
            SET status = 'approved', decided_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (proposal_id,),
        )
        conn.commit()
        return {"preference_id": int(cursor.lastrowid), "event_id": event_id}
    finally:
        conn.close()


@app.post("/preference-proposals/{proposal_id}/reject")
async def reject_preference_proposal(proposal_id: int) -> dict:
    conn = _connect()
    try:
        row = conn.execute(
            """
            SELECT id, conversation_id, key, value, status, causality_message_id
            FROM preference_proposals
            WHERE id = ?
            """,
            (proposal_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Proposal not found")
        if row["status"] != "pending":
            raise HTTPException(status_code=409, detail="Proposal is not pending")

        payload = {
            "actor": "user",
            "proposal_id": int(row["id"]),
            "key": str(row["key"]),
            "value": str(row["value"]),
        }
        event_id = _insert_event(
            conn,
            event_type="preference_rejected",
            payload=payload,
            conversation_id=int(row["conversation_id"]),
            causality_message_id=row["causality_message_id"],
        )
        conn.execute(
            """
            UPDATE preference_proposals
            SET status = 'rejected', decided_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (proposal_id,),
        )
        conn.commit()
        return {"event_id": event_id}
    finally:
        conn.close()


@app.post("/messages")
async def create_message(msg: MessageCreate) -> dict[str, int]:
    content = msg.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Message content is required")

    conn = _connect()
    try:
        conversation_id = msg.conversation_id or _get_latest_conversation_id(conn)
        _ensure_conversation(conn, conversation_id)

        cursor = conn.execute(
            "INSERT INTO messages (content, role, corrects_message_id) VALUES (?, ?, ?)",
            (content, msg.role, msg.corrects_message_id),
        )
        message_id = int(cursor.lastrowid)
        conn.execute(
            "INSERT OR IGNORE INTO conversation_messages (conversation_id, message_id) VALUES (?, ?)",
            (conversation_id, message_id),
        )
        conn.commit()
        return {"id": message_id}
    finally:
        conn.close()


def _sse(payload: dict) -> bytes:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode("utf-8")


@app.post("/chat")
async def chat(req: ChatRequest, request: Request) -> StreamingResponse:
    user_content = req.content.strip()
    if not user_content:
        raise HTTPException(status_code=400, detail="Message content is required")

    conn = _connect()
    try:
        conversation_id = req.conversation_id or _get_latest_conversation_id(conn)
        _ensure_conversation(conn, conversation_id)
        approved_preferences = _load_active_preferences(conn)

        last_msg_role = None
        last_msg_row = conn.execute(
            """
            SELECT role
            FROM messages m
            JOIN conversation_messages cm ON cm.message_id = m.id
            WHERE cm.conversation_id = ?
            ORDER BY m.id DESC
            LIMIT 1
            """,
            (conversation_id,),
        ).fetchone()
        if last_msg_row:
            last_msg_role = last_msg_row["role"]

        decision = evaluate_clarifying_question(
            user_content, previous_message_role=last_msg_role
        )

        cursor = conn.execute(
        "INSERT INTO messages (content, role) VALUES (?, 'user')",
        (user_content,),
        )
        user_message_id = int(cursor.lastrowid)
        conn.execute(
            "INSERT OR IGNORE INTO conversation_messages (conversation_id, message_id) VALUES (?, ?)",
            (conversation_id, user_message_id),
        )
        conn.commit()

        _insert_event(
        conn,
        event_type="user_prompt",
        payload={"content": user_content},
        conversation_id=conversation_id,
        causality_message_id=user_message_id,
        )
        conn.commit()

        rows = conn.execute(
            """
            SELECT m.id, m.content, m.role, m.timestamp, m.corrects_message_id
            FROM messages m
            JOIN conversation_messages cm ON cm.message_id = m.id
            WHERE cm.conversation_id = ?
            ORDER BY m.id
            """,
            (conversation_id,),
        ).fetchall()
        history = [dict(r) for r in rows]

        llm_prompt = model_build_prompt(history, preferences=approved_preferences)
    finally:
        conn.close()

    async def event_stream() -> AsyncIterator[bytes]:
        if decision.action == "clarify":
            conn_q = _connect()
            try:
                cursor_q = conn_q.execute(
                    "INSERT INTO messages (content, role) VALUES (?, 'assistant')",
                    (decision.question,),
                )
                q_message_id = int(cursor_q.lastrowid)
                conn_q.execute(
                    "INSERT OR IGNORE INTO conversation_messages (conversation_id, message_id) VALUES (?, ?)",
                    (conversation_id, q_message_id),
                )
                conn_q.commit()
            finally:
                conn_q.close()

            yield _sse({"token": decision.question})
            yield _sse({"done": True})
            return

        assistant_chunks: list[str] = []
        stopped = False
        proposal_payload: dict | None = None
        trace_id = uuid.uuid4().hex
        request_event_id: int | None = None

        if _llm_logging_enabled():
            log_dir = _llm_log_dir()
            prompt_path = log_dir / f"{trace_id}.prompt.txt"
            _write_text(prompt_path, llm_prompt)
            logger.info("llm_prompt_logged trace_id=%s path=%s", trace_id, prompt_path)

            meta = {
                "trace_id": trace_id,
                "model_url": _get_model_url(),
                "prompt_path": str(prompt_path),
                "prompt_sha256": _sha256_text(llm_prompt),
            }

            conn_log = _connect()
            try:
                request_event_id = _insert_event(
                    conn_log,
                    event_type="llm_request",
                    payload=meta,
                    conversation_id=conversation_id,
                    causality_message_id=user_message_id,
                )
                conn_log.commit()
            finally:
                conn_log.close()

            logger.info(
                "llm_request trace_id=%s event_id=%s prompt_sha256=%s",
                trace_id,
                request_event_id,
                meta["prompt_sha256"],
            )

        try:
            async for token in model_generate(
                history,
                preferences=approved_preferences,
                prompt=llm_prompt,
                model_url=_get_model_url(),
            ):
                if await request.is_disconnected():
                    stopped = True
                    break
                assistant_chunks.append(token)
                yield _sse({"token": token})
        except asyncio.CancelledError:
            stopped = True
        finally:
            raw_assistant_content = "".join(assistant_chunks).strip()
            if stopped and raw_assistant_content:
                raw_assistant_content = f"{raw_assistant_content}\n\n[stopped]"

            cleaned_assistant_content = _truncate_at_role_markers(
                _strip_ansi(_strip_think_blocks(raw_assistant_content)).strip()
            )
            if not cleaned_assistant_content:
                cleaned_assistant_content = _truncate_at_role_markers(
                    _strip_ansi(raw_assistant_content).strip()
                )

            assistant_content = cleaned_assistant_content

            if assistant_content:
                conn2 = _connect()
                try:
                    cursor2 = conn2.execute(
                        "INSERT INTO messages (content, role) VALUES (?, 'assistant')",
                        (assistant_content,),
                    )
                    assistant_message_id = int(cursor2.lastrowid)
                    conn2.execute(
                        "INSERT OR IGNORE INTO conversation_messages (conversation_id, message_id) VALUES (?, ?)",
                        (conversation_id, assistant_message_id),
                    )

                    if not stopped and _get_pending_proposal(conn2, conversation_id) is None:
                        inferred = _infer_preference_proposal(history, approved_preferences)
                        if inferred is not None:
                            cursor3 = conn2.execute(
                                """
                                INSERT INTO preference_proposals (
                                  conversation_id, key, value, proposal_text, rationale,
                                  status, causality_message_id, assistant_message_id
                                )
                                VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
                                """,
                                (
                                    conversation_id,
                                    inferred["key"],
                                    inferred["value"],
                                    inferred["proposal_text"],
                                    inferred.get("rationale"),
                                    user_message_id,
                                    assistant_message_id,
                                ),
                            )
                            proposal_id = int(cursor3.lastrowid)
                            proposal_row = conn2.execute(
                                """
                                SELECT
                                  id, conversation_id, key, value, proposal_text, rationale,
                                  status, created_at, decided_at, causality_message_id, assistant_message_id
                                FROM preference_proposals
                                WHERE id = ?
                                """,
                                (proposal_id,),
                            ).fetchone()
                            if proposal_row is not None:
                                proposal_payload = dict(proposal_row)

                    conn2.commit()
                    _insert_event(
                        conn2,
                        event_type="assistant_response",
                        payload={"content": assistant_content},
                        conversation_id=conversation_id,
                        causality_message_id=assistant_message_id,
                    )
                    conn2.commit()
                finally:
                    conn2.close()
            if assistant_content:
                logger.info(
                    "assistant_response_saved conversation_id=%s",
                    conversation_id,
                )

            if _llm_logging_enabled():
                assistant_full_raw = raw_assistant_content if raw_assistant_content else ""
                assistant_full_cleaned = assistant_content if assistant_content else ""
                log_dir = _llm_log_dir()
                response_path = log_dir / f"{trace_id}.response.txt"
                response_cleaned_path = log_dir / f"{trace_id}.response.cleaned.txt"
                _write_text(response_path, assistant_full_raw)
                _write_text(response_cleaned_path, assistant_full_cleaned)
                logger.info(
                    "llm_response_logged trace_id=%s path=%s",
                    trace_id,
                    response_path,
                )

                meta2 = {
                    "trace_id": trace_id,
                    "request_event_id": request_event_id,
                    "response_path": str(response_path),
                    "response_sha256": _sha256_text(assistant_full_raw),
                    "response_cleaned_path": str(response_cleaned_path),
                    "response_cleaned_sha256": _sha256_text(assistant_full_cleaned),
                    "stopped": stopped,
                }

                conn_log2 = _connect()
                try:
                    response_event_id = _insert_event(
                        conn_log2,
                        event_type="llm_response",
                        payload=meta2,
                        conversation_id=conversation_id,
                        causality_message_id=user_message_id,
                    )
                    conn_log2.commit()
                finally:
                    conn_log2.close()

                logger.info(
                    "llm_response trace_id=%s event_id=%s stopped=%s response_sha256=%s",
                    trace_id,
                    response_event_id,
                    stopped,
                    meta2["response_sha256"],
                )

            if not stopped:
                if proposal_payload is not None:
                    yield _sse({"proposal": proposal_payload})
                yield _sse({"done": True})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/regenerate")
async def regenerate(req: RegenerateRequest, request: Request) -> StreamingResponse:
    conn = _connect()
    try:
        conversation_id = req.conversation_id or _get_latest_conversation_id(conn)
        _ensure_conversation(conn, conversation_id)

        row = conn.execute(
            "SELECT id, content, role FROM messages WHERE id = ?",
            (req.target_message_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Target message not found")
        if row["role"] != "assistant":
            raise HTTPException(
                status_code=400, detail="Target message is not an assistant message"
            )

        rows = conn.execute(
            """
            SELECT m.id, m.content, m.role, m.timestamp, m.corrects_message_id
            FROM messages m
            JOIN conversation_messages cm ON cm.message_id = m.id
            WHERE cm.conversation_id = ?
            ORDER BY m.id
            """,
            (conversation_id,),
        ).fetchall()
        history = [dict(r) for r in rows if r["id"] != req.target_message_id]

        approved_preferences = _load_active_preferences(conn)
        llm_prompt = model_build_prompt(history, preferences=approved_preferences)
    finally:
        conn.close()

    async def event_stream() -> AsyncIterator[bytes]:
        assistant_chunks: list[str] = []
        stopped = False
        trace_id = uuid.uuid4().hex
        request_event_id: int | None = None

        conn_log = _connect()
        try:
            regen_event_id = _insert_event(
                conn_log,
                event_type="regenerate_request",
                payload={"target_message_id": req.target_message_id},
                conversation_id=conversation_id,
                causality_message_id=req.target_message_id,
            )
            conn_log.commit()
        finally:
            conn_log.close()

        if _llm_logging_enabled():
            log_dir = _llm_log_dir()
            prompt_path = log_dir / f"{trace_id}.prompt.txt"
            _write_text(prompt_path, llm_prompt)

            meta = {
                "trace_id": trace_id,
                "model_url": _get_model_url(),
                "prompt_path": str(prompt_path),
                "prompt_sha256": _sha256_text(llm_prompt),
            }

            conn_log = _connect()
            try:
                request_event_id = _insert_event(
                    conn_log,
                    event_type="llm_regenerate_request",
                    payload=meta,
                    conversation_id=conversation_id,
                    causality_message_id=req.target_message_id,
                )
                conn_log.commit()
            finally:
                conn_log.close()

            logger.info(
                "llm_regenerate_request trace_id=%s event_id=%s prompt_sha256=%s",
                trace_id,
                request_event_id,
                meta["prompt_sha256"],
            )

        try:
            async for token in model_generate(
                history,
                preferences=approved_preferences,
                prompt=llm_prompt,
                model_url=_get_model_url(),
            ):
                if await request.is_disconnected():
                    stopped = True
                    break
                assistant_chunks.append(token)
                yield _sse({"token": token})
        except asyncio.CancelledError:
            stopped = True
        finally:
            raw_assistant_content = "".join(assistant_chunks).strip()
            if stopped and raw_assistant_content:
                raw_assistant_content = f"{raw_assistant_content}\n\n[stopped]"

            cleaned_assistant_content = _truncate_at_role_markers(
                _strip_ansi(_strip_think_blocks(raw_assistant_content)).strip()
            )
            if not cleaned_assistant_content:
                cleaned_assistant_content = _truncate_at_role_markers(
                    _strip_ansi(raw_assistant_content).strip()
                )

            assistant_content = cleaned_assistant_content
            if assistant_content:
                conn2 = _connect()
                try:
                    cursor2 = conn2.execute(
                        "INSERT INTO messages (content, role, corrects_message_id) VALUES (?, 'assistant', ?)",
                        (assistant_content, req.target_message_id),
                    )
                    assistant_message_id = int(cursor2.lastrowid)
                    conn2.execute(
                        "INSERT OR IGNORE INTO conversation_messages (conversation_id, message_id) VALUES (?, ?)",
                        (conversation_id, assistant_message_id),
                    )

                    conn2.commit()
                finally:
                    conn2.close()

            if _llm_logging_enabled():
                assistant_full_raw = (
                    raw_assistant_content if raw_assistant_content else ""
                )
                assistant_full_cleaned = assistant_content if assistant_content else ""
                log_dir = _llm_log_dir()
                response_path = log_dir / f"{trace_id}.response.txt"
                response_cleaned_path = log_dir / f"{trace_id}.response.cleaned.txt"
                _write_text(response_path, assistant_full_raw)
                _write_text(response_cleaned_path, assistant_full_cleaned)

                meta2 = {
                    "trace_id": trace_id,
                    "request_event_id": request_event_id,
                    "response_path": str(response_path),
                    "response_sha256": _sha256_text(assistant_full_raw),
                    "response_cleaned_path": str(response_cleaned_path),
                    "response_cleaned_sha256": _sha256_text(assistant_full_cleaned),
                    "stopped": stopped,
                }

                conn_log2 = _connect()
                try:
                    response_event_id = _insert_event(
                        conn_log2,
                        event_type="llm_response",
                        payload=meta2,
                        conversation_id=conversation_id,
                        causality_message_id=req.target_message_id,
                    )
                    conn_log2.commit()
                finally:
                    conn_log2.close()

                logger.info(
                    "llm_response trace_id=%s event_id=%s stopped=%s response_sha256=%s",
                    trace_id,
                    response_event_id,
                    stopped,
                    meta2["response_sha256"],
                )

            if not stopped:
                yield _sse({"done": True})

    return StreamingResponse(event_stream(), media_type="text/event-stream")
