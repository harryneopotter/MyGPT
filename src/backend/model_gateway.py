from __future__ import annotations

import json
import os
import hashlib
import logging
from pathlib import Path
from typing import AsyncGenerator
import re

import httpx
import asyncio

DEFAULT_MODEL_URL = "http://127.0.0.1:8080"


REPO_ROOT = Path(__file__).resolve().parents[2]
SYSTEM_DIR = REPO_ROOT / "system"
BASE_SYSTEM_PROMPT_PATH = SYSTEM_DIR / "base_assistant_prompt.md"
BASE_SYSTEM_PROMPT_SHA256_PATH = SYSTEM_DIR / "base_assistant_prompt.sha256"


def _load_base_system_prompt() -> str:
    return BASE_SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")


def _load_expected_base_prompt_sha256() -> str:
    return BASE_SYSTEM_PROMPT_SHA256_PATH.read_text(encoding="utf-8").strip().lower()


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


BASE_SYSTEM_PROMPT = _load_base_system_prompt()
BASE_SYSTEM_PROMPT_SHA256 = hashlib.sha256(BASE_SYSTEM_PROMPT_PATH.read_bytes()).hexdigest()
EXPECTED_BASE_SYSTEM_PROMPT_SHA256 = _load_expected_base_prompt_sha256()

if BASE_SYSTEM_PROMPT_SHA256 != EXPECTED_BASE_SYSTEM_PROMPT_SHA256:
    raise RuntimeError(
        "Base system prompt hash mismatch. "
        f"expected={EXPECTED_BASE_SYSTEM_PROMPT_SHA256} actual={BASE_SYSTEM_PROMPT_SHA256} "
        f"path={BASE_SYSTEM_PROMPT_PATH}"
    )

logging.getLogger("mygpt").info(
    "Base system prompt loaded sha256=%s path=%s",
    BASE_SYSTEM_PROMPT_SHA256,
    str(BASE_SYSTEM_PROMPT_PATH),
)


def _assemble_prompt(messages: list[dict], preferences: dict[str, str] | None = None) -> str:
    def _indent_block(text: str, prefix: str = "  ") -> str:
        lines = str(text).splitlines()
        if not lines:
            return prefix
        return "\n".join(prefix + line for line in lines)

    def _sanitize_assistant_history(text: str) -> str:
        # Keep assistant history as close as possible to what was said, but remove
        # obvious transcript artifacts and reasoning wrappers that can cause the
        # model to "continue the log" instead of answering.
        s = str(text)
        s = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", s)
        # Strip reasoning blocks, including cases where the close tag is missing due to truncation.
        s = re.sub(r"<think>.*?(</think>|$)", "", s, flags=re.DOTALL)
        s = re.sub(r"〈thinking〉.*?(〈/thinking〉|$)", "", s, flags=re.DOTALL)
        s = re.sub(r"＜thinking＞.*?(＜/thinking＞|$)", "", s, flags=re.DOTALL)
        lines = []
        for line in s.splitlines():
            if line.startswith("User:") or line.startswith("Assistant:") or line.startswith("System:"):
                continue
            lines.append(line)
        return "\n".join(lines).strip()

    prompt_parts: list[str] = []

    base = BASE_SYSTEM_PROMPT.rstrip()
    prompt_parts.append(f"System: {base.replace(chr(10), chr(10) + 'System: ')}")
    prompt_parts.append(
        "System: Reply as the assistant only. Do not write any 'User:' lines or simulate additional turns."
    )
    prompt_parts.append(
        "System: Do not output internal reasoning or thinking (e.g., <think>, 〈thinking〉). Provide only the final answer."
    )
    if preferences:
        defaults = ", ".join(f"{k}={v}" for k, v in sorted(preferences.items()))
        prompt_parts.append(
            f"System: Defaults (apply only when user did not specify otherwise): {defaults}"
        )

    for msg in messages:
        role = msg.get("role")
        content = msg.get("content", "")
        if role == "user":
            prompt_parts.append("User:")
            prompt_parts.append(_indent_block(content))
        elif role == "assistant":
            cleaned = _sanitize_assistant_history(content)
            if not cleaned:
                continue
            prompt_parts.append("Assistant:")
            prompt_parts.append(_indent_block(cleaned))

    prompt_parts.append("Assistant:")
    return "\n".join(prompt_parts) + " "


def build_prompt(messages: list[dict], preferences: dict[str, str] | None = None) -> str:
    return _assemble_prompt(messages, preferences=preferences)


def _default_stop_sequences() -> list[str]:
    return [
        "\nUser:",
        "\r\nUser:",
        "\nSystem:",
        "\r\nSystem:",
    ]


def _parse_stop_sequences(raw: str) -> list[str]:
    # Accept JSON list or a newline-separated string.
    value = raw.strip()
    if not value:
        return []
    if value.startswith("["):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(x) for x in parsed if str(x)]
        except Exception:
            return []
    return [line for line in (s.strip() for s in value.splitlines()) if line]


async def _fallback_generate(messages: list[dict]) -> AsyncGenerator[str, None]:
    last_user = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            last_user = str(msg.get("content", ""))
            break
    text = f"(no model server) Echo: {last_user}".strip()
    delay_s = float(os.getenv("MYGPT_FALLBACK_STREAM_DELAY_S", "0.05"))
    for word in text.split():
        yield f"{word} "
        await asyncio.sleep(delay_s)


async def generate(
    messages: list[dict],
    preferences: dict[str, str] | None = None,
    prompt: str | None = None,
    model_url: str | None = None,
) -> AsyncGenerator[str, None]:
    """
    Streams tokens from a local llama.cpp-style HTTP server. If the server is
    unreachable, falls back to a deterministic local echo.
    """

    model_url = (model_url or os.getenv("MYGPT_MODEL_URL", DEFAULT_MODEL_URL)).rstrip("/")
    prompt_text = prompt if prompt is not None else build_prompt(messages, preferences=preferences)

    payload = {
        "prompt": prompt_text,
        "stream": True,
        "n_predict": int(os.getenv("MYGPT_N_PREDICT", "256")),
    }

    # llama.cpp server supports disabling "reasoning" wrappers for some models.
    # Default to "none" to avoid verbose 〈thinking〉 blocks consuming output tokens.
    payload["reasoning_format"] = os.getenv("MYGPT_REASONING_FORMAT", "none").strip() or "none"
    payload["reasoning_in_content"] = os.getenv("MYGPT_REASONING_IN_CONTENT", "false").strip().lower() == "true"

    stop_env = os.getenv("MYGPT_STOP_SEQS", "").strip()
    stop_seqs = _parse_stop_sequences(stop_env) if stop_env else _default_stop_sequences()
    if stop_seqs:
        payload["stop"] = stop_seqs

    try:
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                f"{model_url}/completion",
                json=payload,
                headers={"Accept": "text/event-stream"},
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    if not line.startswith("data:"):
                        continue
                    data_str = line[len("data:") :].strip()
                    if not data_str:
                        continue
                    if data_str == "[DONE]":
                        break

                    data = json.loads(data_str)
                    token = data.get("content")
                    if token:
                        yield str(token)
                    if data.get("stop") is True:
                        break
    except Exception:
        async for token in _fallback_generate(messages):
            yield token


async def embed(text: str) -> None:
    raise NotImplementedError("embed() not implemented yet")


async def vision(image: str) -> None:
    raise NotImplementedError("vision() not implemented yet")
