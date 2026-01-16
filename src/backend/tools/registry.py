from __future__ import annotations

from dataclasses import dataclass
import asyncio
import os
import re
import shutil
import sqlite3
import time
from pathlib import Path
from typing import Callable, Awaitable
from urllib.parse import urlparse, unquote


@dataclass(frozen=True)
class ToolDefinition:
    tool_id: str
    description: str
    input_schema: dict
    output_schema: dict
    requires_confirmation: bool = False
    requires_network: bool = False
    handler: Callable[[dict, "ToolContext"], Awaitable[dict]] | None = None


@dataclass(frozen=True)
class ToolContext:
    repo_root: Path
    db_path: Path
    allowed_roots: list[Path]
    allow_network: bool
    command_allowlist: set[str]
    max_output_bytes: int
    command_timeout_sec: int


def _resolve_path(path_value: str, roots: list[Path]) -> Path:
    raw_path = Path(path_value)
    if not raw_path.is_absolute():
        raw_path = roots[0] / raw_path
    resolved = raw_path.resolve()
    for root in roots:
        try:
            resolved.relative_to(root)
            return resolved
        except ValueError:
            continue
    raise ValueError("Path is outside allowed roots.")


def _normalize_allowlist(values: str) -> set[str]:
    allowlist: set[str] = set()
    for raw in values.split(os.pathsep):
        item = raw.strip()
        if not item:
            continue
        allowlist.add(item.lower())
        allowlist.add(Path(item).name.lower())
    return allowlist


async def _run_subprocess(
    cmd: list[str],
    *,
    input_text: str | None = None,
    timeout_sec: int,
    max_output_bytes: int,
    cwd: Path,
) -> dict:
    start = time.time()
    
    # Create subprocess
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE if input_text else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(cwd),
    )

    try:
        stdout_data, stderr_data = await asyncio.wait_for(
            process.communicate(input=input_text.encode() if input_text else None),
            timeout=timeout_sec
        )
    except asyncio.TimeoutError:
        try:
            process.kill()
        except ProcessLookupError:
            pass
        raise ValueError(f"Command timed out after {timeout_sec}s")

    duration = time.time() - start
    stdout = stdout_data.decode("utf-8", errors="replace")
    stderr = stderr_data.decode("utf-8", errors="replace")
    
    truncated = False
    if len(stdout) + len(stderr) > max_output_bytes:
        truncated = True
        keep = max_output_bytes // 2
        stdout = stdout[:keep]
        stderr = stderr[: max_output_bytes - keep]
        
    return {
        "exit_code": process.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "truncated": truncated,
        "duration_sec": round(duration, 4),
    }


async def _tool_list_dir(tool_input: dict, ctx: ToolContext) -> dict:
    target = tool_input.get("path", str(ctx.repo_root))
    recursive = bool(tool_input.get("recursive", False))
    max_entries = int(tool_input.get("max_entries", 2000))
    resolved = _resolve_path(target, ctx.allowed_roots)
    if not resolved.exists():
        raise ValueError("Path does not exist.")
    if not resolved.is_dir():
        raise ValueError("Path is not a directory.")

    entries = []
    # Using asyncio.to_thread for potentially slow file IO operations
    def _list():
        iterator = resolved.rglob("*") if recursive else resolved.iterdir()
        local_entries = []
        for entry in iterator:
            local_entries.append(
                {
                    "name": entry.name,
                    "path": str(entry),
                    "type": "dir" if entry.is_dir() else "file",
                }
            )
            if len(local_entries) >= max_entries:
                break
        return local_entries

    entries = await asyncio.to_thread(_list)
    return {"path": str(resolved), "entries": entries, "truncated": len(entries) >= max_entries}


async def _tool_read_file(tool_input: dict, ctx: ToolContext) -> dict:
    path_value = tool_input.get("path")
    if not path_value:
        raise ValueError("Missing path.")
    max_bytes = int(tool_input.get("max_bytes", 200_000))
    resolved = _resolve_path(path_value, ctx.allowed_roots)
    if not resolved.exists() or not resolved.is_file():
        raise ValueError("Path does not exist or is not a file.")
    
    data = await asyncio.to_thread(resolved.read_bytes)
    truncated = False
    if len(data) > max_bytes:
        data = data[:max_bytes]
        truncated = True
    content = data.decode("utf-8", errors="replace")
    return {
        "path": str(resolved),
        "content": content,
        "bytes": len(data),
        "truncated": truncated,
    }


async def _tool_search_text(tool_input: dict, ctx: ToolContext) -> dict:
    pattern = tool_input.get("pattern")
    if not pattern:
        raise ValueError("Missing pattern.")
    target = tool_input.get("path", str(ctx.repo_root))
    max_matches = int(tool_input.get("max_matches", 2000))
    resolved = _resolve_path(target, ctx.allowed_roots)
    if not resolved.exists():
        raise ValueError("Path does not exist.")

    rg_path = shutil.which("rg")
    matches: list[dict] = []
    truncated = False
    
    if rg_path:
        cmd = [
            rg_path,
            "--column",
            "--line-number",
            "--no-heading",
            "--max-count",
            str(max_matches),
            pattern,
            str(resolved),
        ]
        result = await _run_subprocess(
            cmd,
            timeout_sec=ctx.command_timeout_sec,
            max_output_bytes=ctx.max_output_bytes,
            cwd=ctx.repo_root,
        )
        if result["exit_code"] not in (0, 1):
            raise ValueError(result["stderr"] or "Search failed.")
        for line in result["stdout"].splitlines():
            parts = line.split(":", 3)
            if len(parts) < 4:
                continue
            matches.append(
                {
                    "path": parts[0],
                    "line": int(parts[1]),
                    "column": int(parts[2]),
                    "match": parts[3],
                }
            )
            if len(matches) >= max_matches:
                truncated = True
                break
    else:
        # Fallback to python search in thread
        def _search():
            local_matches = []
            local_truncated = False
            for file_path in resolved.rglob("*"):
                if not file_path.is_file():
                    continue
                try:
                    text = file_path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                for idx, line in enumerate(text.splitlines(), start=1):
                    if pattern in line:
                        local_matches.append(
                            {
                                "path": str(file_path),
                                "line": idx,
                                "column": line.find(pattern) + 1,
                                "match": line,
                            }
                        )
                        if len(local_matches) >= max_matches:
                            local_truncated = True
                            break
                if local_truncated:
                    break
            return local_matches, local_truncated

        matches, truncated = await asyncio.to_thread(_search)

    return {"pattern": pattern, "matches": matches, "truncated": truncated}


async def _tool_stat_path(tool_input: dict, ctx: ToolContext) -> dict:
    path_value = tool_input.get("path")
    if not path_value:
        raise ValueError("Missing path.")
    resolved = _resolve_path(path_value, ctx.allowed_roots)
    exists = resolved.exists()
    if not exists:
        return {"path": str(resolved), "exists": False}
    info = await asyncio.to_thread(resolved.stat)
    return {
        "path": str(resolved),
        "exists": True,
        "type": "dir" if resolved.is_dir() else "file",
        "size": info.st_size,
        "modified_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(info.st_mtime)),
    }


async def _tool_write_file(tool_input: dict, ctx: ToolContext) -> dict:
    path_value = tool_input.get("path")
    content = tool_input.get("content")
    if not path_value:
        raise ValueError("Missing path.")
    if content is None:
        raise ValueError("Missing content.")
    mode = tool_input.get("mode", "overwrite")
    if mode not in {"overwrite", "append"}:
        raise ValueError("Invalid mode.")
    resolved = _resolve_path(path_value, ctx.allowed_roots)
    
    def _write():
        resolved.parent.mkdir(parents=True, exist_ok=True)
        open_mode = "a" if mode == "append" else "w"
        with resolved.open(open_mode, encoding="utf-8") as handle:
            handle.write(str(content))
            
    await asyncio.to_thread(_write)
    return {"path": str(resolved), "bytes_written": len(str(content))}


async def _tool_git_status(tool_input: dict, ctx: ToolContext) -> dict:
    git_path = shutil.which("git")
    if not git_path:
        raise ValueError("git not found.")
    result = await _run_subprocess(
        [git_path, "status", "-sb"],
        timeout_sec=ctx.command_timeout_sec,
        max_output_bytes=ctx.max_output_bytes,
        cwd=ctx.repo_root,
    )
    return result


async def _tool_git_diff(tool_input: dict, ctx: ToolContext) -> dict:
    git_path = shutil.which("git")
    if not git_path:
        raise ValueError("git not found.")
    staged = bool(tool_input.get("staged", False))
    path_value = tool_input.get("path")
    cmd = [git_path, "diff"]
    if staged:
        cmd.append("--staged")
    if path_value:
        resolved = _resolve_path(path_value, ctx.allowed_roots)
        cmd.extend(["--", str(resolved)])
    result = await _run_subprocess(
        cmd,
        timeout_sec=ctx.command_timeout_sec,
        max_output_bytes=ctx.max_output_bytes,
        cwd=ctx.repo_root,
    )
    return result


async def _tool_git_show(tool_input: dict, ctx: ToolContext) -> dict:
    git_path = shutil.which("git")
    if not git_path:
        raise ValueError("git not found.")
    ref = str(tool_input.get("ref", "HEAD"))
    cmd = [git_path, "show", ref]
    result = await _run_subprocess(
        cmd,
        timeout_sec=ctx.command_timeout_sec,
        max_output_bytes=ctx.max_output_bytes,
        cwd=ctx.repo_root,
    )
    return result


async def _tool_apply_patch(tool_input: dict, ctx: ToolContext) -> dict:
    patch_text = tool_input.get("patch")
    if not patch_text:
        raise ValueError("Missing patch.")
    git_path = shutil.which("git")
    if not git_path:
        raise ValueError("git not found.")
    cmd = [git_path, "apply", "--whitespace=nowarn", "-"]
    result = await _run_subprocess(
        cmd,
        input_text=str(patch_text),
        timeout_sec=ctx.command_timeout_sec,
        max_output_bytes=ctx.max_output_bytes,
        cwd=ctx.repo_root,
    )
    return result


async def _tool_sql_query(tool_input: dict, ctx: ToolContext) -> dict:
    query = tool_input.get("query")
    if not query:
        raise ValueError("Missing query.")
    normalized = str(query).strip()
    normalized_no_semicolon = normalized.rstrip(";")
    if ";" in normalized_no_semicolon:
        raise ValueError("Multiple statements are not allowed.")
    if not re.match(r"(?is)^(select|with)\b", normalized_no_semicolon):
        raise ValueError("Only SELECT queries are allowed.")
    max_rows = int(tool_input.get("max_rows", 200))
    
    def _query():
        conn = sqlite3.connect(f"file:{ctx.db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.execute(normalized_no_semicolon)
            rows = cursor.fetchmany(max_rows + 1)
            truncated = len(rows) > max_rows
            if truncated:
                rows = rows[:max_rows]
            result_rows = [dict(row) for row in rows]
            return result_rows, truncated
        finally:
            conn.close()
            
    rows, truncated = await asyncio.to_thread(_query)
    return {"rows": rows, "truncated": truncated, "row_count": len(rows)}


async def _tool_open_url(tool_input: dict, ctx: ToolContext) -> dict:
    url = tool_input.get("url")
    if not url:
        raise ValueError("Missing url.")
    parsed = urlparse(url)
    if parsed.scheme == "file":
        path_value = unquote(parsed.path)
        resolved = _resolve_path(path_value, ctx.allowed_roots)
        return {
            "url": f"file://{resolved}",
            "requires_user_action": True,
        }
    if not parsed.scheme:
        raise ValueError("URL must include a scheme.")
    return {"url": url, "requires_user_action": True}


async def _tool_run_command(tool_input: dict, ctx: ToolContext) -> dict:
    command = tool_input.get("command")
    args = tool_input.get("args", [])
    if not command:
        raise ValueError("Missing command.")
    if not isinstance(args, list):
        raise ValueError("args must be a list.")
    command_name = Path(str(command)).name.lower()
    if command_name not in ctx.command_allowlist and str(command).lower() not in ctx.command_allowlist:
        raise ValueError("Command is not allowlisted.")
    cmd = [str(command)] + [str(arg) for arg in args]
    result = await _run_subprocess(
        cmd,
        timeout_sec=ctx.command_timeout_sec,
        max_output_bytes=ctx.max_output_bytes,
        cwd=ctx.repo_root,
    )
    return result


def get_tool_definitions() -> list[ToolDefinition]:
    return [
        ToolDefinition(
            tool_id="list_dir",
            description="List directory contents within allowed roots.",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "recursive": {"type": "boolean"},
                    "max_entries": {"type": "integer"},
                },
                "additionalProperties": False,
            },
            output_schema={"type": "object"},
            handler=_tool_list_dir,
        ),
        ToolDefinition(
            tool_id="read_file",
            description="Read a text file within allowed roots.",
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string"}, "max_bytes": {"type": "integer"}},
                "required": ["path"],
                "additionalProperties": False,
            },
            output_schema={"type": "object"},
            handler=_tool_read_file,
        ),
        ToolDefinition(
            tool_id="search_text",
            description="Search text within allowed roots.",
            input_schema={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string"},
                    "path": {"type": "string"},
                    "max_matches": {"type": "integer"},
                },
                "required": ["pattern"],
                "additionalProperties": False,
            },
            output_schema={"type": "object"},
            handler=_tool_search_text,
        ),
        ToolDefinition(
            tool_id="stat_path",
            description="Return metadata for a path within allowed roots.",
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            },
            output_schema={"type": "object"},
            handler=_tool_stat_path,
        ),
        ToolDefinition(
            tool_id="write_file",
            description="Write text content to a file within allowed roots.",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                    "mode": {"type": "string", "enum": ["overwrite", "append"]},
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
            output_schema={"type": "object"},
            requires_confirmation=True,
            handler=_tool_write_file,
        ),
        ToolDefinition(
            tool_id="git_status",
            description="Run git status -sb for the repository.",
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
            output_schema={"type": "object"},
            handler=_tool_git_status,
        ),
        ToolDefinition(
            tool_id="git_diff",
            description="Run git diff for the repository.",
            input_schema={
                "type": "object",
                "properties": {"staged": {"type": "boolean"}, "path": {"type": "string"}},
                "additionalProperties": False,
            },
            output_schema={"type": "object"},
            handler=_tool_git_diff,
        ),
        ToolDefinition(
            tool_id="git_show",
            description="Run git show for a ref.",
            input_schema={
                "type": "object",
                "properties": {"ref": {"type": "string"}},
                "additionalProperties": False,
            },
            output_schema={"type": "object"},
            handler=_tool_git_show,
        ),
        ToolDefinition(
            tool_id="apply_patch",
            description="Apply a unified diff patch in the repository.",
            input_schema={
                "type": "object",
                "properties": {"patch": {"type": "string"}},
                "required": ["patch"],
                "additionalProperties": False,
            },
            output_schema={"type": "object"},
            requires_confirmation=True,
            handler=_tool_apply_patch,
        ),
        ToolDefinition(
            tool_id="sql_query",
            description="Run a read-only SQL query against the local SQLite DB.",
            input_schema={
                "type": "object",
                "properties": {"query": {"type": "string"}, "max_rows": {"type": "integer"}},
                "required": ["query"],
                "additionalProperties": False,
            },
            output_schema={"type": "object"},
            handler=_tool_sql_query,
        ),
        ToolDefinition(
            tool_id="open_url",
            description="Return a URL that requires explicit user action to open.",
            input_schema={
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
                "additionalProperties": False,
            },
            output_schema={"type": "object"},
            requires_confirmation=True,
            handler=_tool_open_url,
        ),
        ToolDefinition(
            tool_id="run_command",
            description="Run an allowlisted command with args.",
            input_schema={
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "args": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["command"],
                "additionalProperties": False,
            },
            output_schema={"type": "object"},
            requires_confirmation=True,
            handler=_tool_run_command,
        ),
    ]


async def run_tool(tool_id: str, tool_input: dict, ctx: ToolContext, *, confirmed: bool) -> dict:
    tool_map = {tool.tool_id: tool for tool in get_tool_definitions()}
    tool = tool_map.get(tool_id)
    if tool is None:
        raise ValueError("Unknown tool.")
    if tool.requires_network and not ctx.allow_network:
        raise ValueError("Network tools are disabled.")
    if tool.requires_confirmation and not confirmed:
        raise ValueError("Tool requires explicit confirmation.")
    if tool.handler is None:
        raise ValueError("Tool has no handler.")
    return await tool.handler(tool_input, ctx)


def build_tool_context(repo_root: Path, db_path: Path) -> ToolContext:
    allowed_roots_raw = os.getenv("MYGPT_TOOL_ROOTS", str(repo_root))
    allowed_roots = [Path(p).resolve() for p in allowed_roots_raw.split(os.pathsep) if p.strip()]
    if not allowed_roots:
        allowed_roots = [repo_root.resolve()]
    allow_network = os.getenv("MYGPT_ALLOW_NETWORK_TOOLS", "0") == "1"
    allowlist_raw = os.getenv("MYGPT_TOOL_COMMAND_ALLOWLIST", "")
    command_allowlist = _normalize_allowlist(allowlist_raw)
    max_output_bytes = int(os.getenv("MYGPT_TOOL_MAX_OUTPUT_BYTES", "200000"))
    command_timeout_sec = int(os.getenv("MYGPT_TOOL_COMMAND_TIMEOUT", "10"))
    return ToolContext(
        repo_root=repo_root.resolve(),
        db_path=db_path.resolve(),
        allowed_roots=allowed_roots,
        allow_network=allow_network,
        command_allowlist=command_allowlist,
        max_output_bytes=max_output_bytes,
        command_timeout_sec=command_timeout_sec,
    )
