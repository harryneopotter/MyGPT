from __future__ import annotations

      import json
      import os
      import sqlite3
      import uuid
      import hashlib
      import logging
      from pathlib import Path
      from typing import AsyncIterator, Literal

      import asyncio
      from fastapi import FastAPI, HTTPException, Query, Request
      from fastapi.middleware.cors import CORSMiddleware
      from fastapi.responses import StreamingResponse
      from pydantic import BaseModel, Field

      from .model_gateway import build_prompt as model_build_prompt
      from .model_gateway import generate as model_generate

      app = FastAPI(title="Logical Low-Friction AI Chat Backend")
      logger = logging.getLogger("mygpt")

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

      REPO_ROOT = Path(__file__).resolve().parents[2]
      DATA_DIR = Path(os.getenv("MYGPT_DATA_DIR", str(REPO_ROOT / "data")))
      DB_PATH = Path(os.getenv("MYGPT_DB_PATH", str(DATA_DIR / "chat.db")))
      SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


      def _connect() -> sqlite3.Connection:
          DATA_DIR.mkdir(parents=True, exist_ok=True)
          conn = sqlite3.connect(DB_PATH)
          conn.row_factory = sqlite3.Row
          return conn


      def _llm_logging_enabled() -> bool:
          return os.getenv("MYGPT_LOG_LLM", "0").strip() == "1"


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
              assistant_chunks: list[str] = []
              stopped = False
              proposal_payload: dict | None = None
              trace_id = uuid.uuid4().hex
              request_event_id: int | None = None

              if _llm_logging_enabled():
                  log_dir = _llm_log_dir()
                  prompt_path = log_dir / f"{trace_id}.prompt.txt"
                  _write_text(prompt_path, llm_prompt)

                  meta = {
                      "trace_id": trace_id,
                      "model_url": os.getenv("MYGPT_MODEL_URL", ""),
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
                      finally:
                          conn2.close()

                  if _llm_logging_enabled():
                      assistant_full_raw = raw_assistant_content if raw_assistant_content else ""
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
                  prompt_path = log_dir / f"{trace_id}.prompt.txt}"
                  _write_text(prompt_path, llm_prompt)

                  meta = {
                      "trace_id": trace_id,
                      "model_url": os.getenv("MYGPT_MODEL_URL", ""),
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
                      response_path = log_dir / f"{trace_id}.response.txt}"
                      response_cleaned_path = log_dir / f"{trace_id}.response.cleaned.txt}"
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