import os
import sqlite3
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pathlib import Path

# Set env vars before importing app to use tmp db
# We use a fixture to handle this cleanly, but importing app at top level 
# might trigger init_db on the default path if we aren't careful.
# app.py calls init_db() at module level? Yes.
# So we need to set the env var *before* import.
# But we can't easily do that in a test file if we import at top level.
# So we will set os.environ here before import.

os.environ["MYGPT_DB_PATH"] = ":memory:" # Use memory db for tests? 
# Wait, app.py `init_db` closes the connection, so :memory: will be lost.
# We need a file path.

import tempfile
temp_db = tempfile.NamedTemporaryFile(delete=False)
temp_db.close()
os.environ["MYGPT_DB_PATH"] = temp_db.name

from src.backend.app import app
import src.backend.app as app_module

client = TestClient(app)

def teardown_module():
    try:
        os.unlink(temp_db.name)
    except:
        pass

def test_message_immutability():
    # 1. Create a message
    res = client.post("/messages", json={"role": "user", "content": "original"})
    assert res.status_code == 200
    msg_id = res.json()["id"]

    # 2. Verify it's there
    conn = sqlite3.connect(temp_db.name)
    row = conn.execute("SELECT content FROM messages WHERE id=?", (msg_id,)).fetchone()
    assert row[0] == "original"

    # 3. Try to update it - should fail via Trigger
    with pytest.raises(sqlite3.IntegrityError, match="Messages are immutable"):
        conn.execute("UPDATE messages SET content='edited' WHERE id=?", (msg_id,))
    
    # 4. Try to delete it - should fail
    with pytest.raises(sqlite3.IntegrityError, match="Messages are immutable"):
        conn.execute("DELETE FROM messages WHERE id=?", (msg_id,))
    
    conn.close()

def test_full_conversation_flow():
    # 1. Create conversation
    res = client.post("/conversations", json={"title": "Integration Test"})
    assert res.status_code == 200
    conv_id = res.json()["id"]

    # 2. Add user message
    res = client.post("/chat", json={"conversation_id": conv_id, "content": "Hello"})
    assert res.status_code == 200
    # The output is SSE, so we check if it started streaming
    assert "text/event-stream" in res.headers["content-type"]
    
    # consume stream
    content = ""
    for line in res.iter_lines():
        if line.startswith("data: "):
            import json
            data = json.loads(line[6:])
            if "token" in data:
                content += data["token"]
    
    # Since we don't have a real model running, it should fallback to echo
    # "Echo: Hello" (from model_gateway.py _fallback_generate)
    assert "Echo: Hello" in content

    # 3. Check history
    res = client.get(f"/messages?conversation_id={conv_id}")
    assert res.status_code == 200
    msgs = res.json()
    assert len(msgs) == 2 # User + Assistant
    assert msgs[0]["content"] == "Hello"
    assert "Echo: Hello" in msgs[1]["content"]


def _read_sse_events(response) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in response.iter_lines():
        if not line.startswith("data: "):
            continue
        import json
        payload = json.loads(line[6:])
        events.append(payload)
    return events


def test_preference_proposal_after_tokens():
    res = client.post("/conversations", json={"title": "Proposal Order"})
    assert res.status_code == 200
    conv_id = res.json()["id"]

    res = client.post("/chat", json={"conversation_id": conv_id, "content": "Please be concise."})
    assert res.status_code == 200
    _read_sse_events(res)

    res = client.post("/chat", json={"conversation_id": conv_id, "content": "Keep it concise."})
    assert res.status_code == 200
    events = _read_sse_events(res)

    event_types = []
    for event in events:
        if "token" in event:
            event_types.append("token")
        if "proposal" in event:
            event_types.append("proposal")
        if "done" in event:
            event_types.append("done")

    assert "proposal" in event_types
    last_token_idx = max(i for i, t in enumerate(event_types) if t == "token")
    proposal_idx = event_types.index("proposal")
    assert proposal_idx > last_token_idx


def test_pending_proposal_does_not_affect_prompt(monkeypatch):
    captured = {}

    def fake_build_prompt(history, preferences=None):
        captured["preferences"] = dict(preferences or {})
        return "PROMPT"

    async def fake_generate(*args, **kwargs):
        yield "ok "

    monkeypatch.setattr(app_module, "model_build_prompt", fake_build_prompt)
    monkeypatch.setattr(app_module, "model_generate", fake_generate)

    res = client.post("/conversations", json={"title": "Pending Proposal"})
    assert res.status_code == 200
    conv_id = res.json()["id"]

    conn = sqlite3.connect(temp_db.name)
    conn.execute(
        """
        INSERT INTO preference_proposals (conversation_id, key, value, proposal_text, rationale, status)
        VALUES (?, ?, ?, ?, ?, 'pending')
        """,
        (conv_id, "verbosity", "concise", "Prefer concise answers by default.", "test"),
    )
    conn.commit()
    conn.close()

    res = client.post("/chat", json={"conversation_id": conv_id, "content": "Hello"})
    assert res.status_code == 200
    _read_sse_events(res)

    assert captured.get("preferences") == {}
    conn = sqlite3.connect(temp_db.name)
    pref_count = conn.execute("SELECT COUNT(*) FROM preferences").fetchone()[0]
    conn.close()
    assert pref_count == 0
