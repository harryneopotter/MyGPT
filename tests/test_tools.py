from pathlib import Path
import sqlite3

import pytest

from src.backend.tools.registry import ToolContext, run_tool


def _make_ctx(tmp_path: Path, db_path: Path) -> ToolContext:
    return ToolContext(
        repo_root=tmp_path,
        db_path=db_path,
        allowed_roots=[tmp_path],
        allow_network=False,
        command_allowlist=set(),
        max_output_bytes=200000,
        command_timeout_sec=5,
    )


@pytest.mark.anyio
async def test_read_file_blocks_outside_allowed_roots(tmp_path: Path) -> None:
    inside = tmp_path / "inside.txt"
    inside.write_text("ok", encoding="utf-8")

    outside_dir = tmp_path.parent / "outside"
    outside_dir.mkdir(exist_ok=True)
    outside = outside_dir / "secret.txt"
    outside.write_text("nope", encoding="utf-8")

    ctx = _make_ctx(tmp_path, tmp_path / "db.sqlite")

    ok = await run_tool("read_file", {"path": str(inside)}, ctx, confirmed=True)
    assert "content" in ok

    with pytest.raises(ValueError, match="outside allowed roots"):
        await run_tool("read_file", {"path": str(outside)}, ctx, confirmed=True)


@pytest.mark.anyio
async def test_sql_query_read_only(tmp_path: Path) -> None:
    db_path = tmp_path / "chat.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE demo (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO demo (name) VALUES ('alpha')")
    conn.commit()
    conn.close()

    ctx = _make_ctx(tmp_path, db_path)

    result = await run_tool("sql_query", {"query": "SELECT * FROM demo"}, ctx, confirmed=True)
    assert result["row_count"] == 1

    with pytest.raises(ValueError, match="Only SELECT"):
        await run_tool("sql_query", {"query": "DELETE FROM demo"}, ctx, confirmed=True)

    with pytest.raises(ValueError, match="Multiple statements"):
        await run_tool("sql_query", {"query": "SELECT 1; SELECT 2"}, ctx, confirmed=True)
