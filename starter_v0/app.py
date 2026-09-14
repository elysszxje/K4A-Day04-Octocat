from __future__ import annotations

import os
import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any, Callable
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from chat import now_iso, run_model_tool_loop, trim_history, write_transcript
from env_loader import load_lab_env
from providers import make_provider
from tools import load_tool_declarations, to_openai_tools
from versioning import artifact_version_dict, build_artifact_version


ROOT = Path(__file__).parent
ARTIFACTS_DIR = ROOT / "artifacts"
SYSTEM_PROMPT_PATH = ARTIFACTS_DIR / "system_prompt.md"
TOOLS_PATH = ARTIFACTS_DIR / "tools.yaml"
DATA_DIR = ROOT / "data"
TRANSCRIPTS_DIR = ROOT / "transcripts"
PREVIEW_PATH = ROOT / "samples" / "transcripts" / "example_helpdesk.transcript.json"
FRONTEND_DIST = ROOT / "frontend" / "dist"

DEFAULT_PROVIDER_NAME = "gemini"
DEMO_PROVIDER_NAME = "demo"
DEFAULT_VERSION = "v3"
DEFAULT_HISTORY_WINDOW = 5
DEFAULT_MAX_TOOL_ROUNDS = 4

load_lab_env(ROOT)

app = FastAPI(title="IT Helpdesk Agent", version="1.0.0")


class SessionCreate(BaseModel):
    version: str = Field(default=DEFAULT_VERSION, min_length=1, max_length=32)
    model: str | None = Field(default=None, max_length=128)
    history_window: int = Field(default=DEFAULT_HISTORY_WINDOW, ge=1, le=20)
    max_tool_rounds: int = Field(default=DEFAULT_MAX_TOOL_ROUNDS, ge=1, le=10)


class MessageCreate(BaseModel):
    message: str = Field(min_length=1, max_length=8_000)


@dataclass
class ChatSession:
    transcript: dict[str, Any]
    history: list[dict[str, str]] = field(default_factory=list)
    lock: Lock = field(default_factory=Lock)


SESSIONS: dict[str, ChatSession] = {}
SESSIONS_LOCK = Lock()


def live_available() -> bool:
    if demo_enabled():
        return False
    required_keys = {
        "gemini": "GEMINI_API_KEY",
        "ninerouter": "NINEROUTER_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
    }
    key_name = required_keys.get(configured_provider_name())
    return bool(key_name and os.getenv(key_name))


def demo_enabled() -> bool:
    return os.getenv("DEMO_MODE", "").strip().lower() in {"1", "true", "yes", "on"}


def active_provider_name() -> str:
    return DEMO_PROVIDER_NAME if demo_enabled() else configured_provider_name()


def configured_provider_name() -> str:
    return os.getenv("AGENT_PROVIDER", DEFAULT_PROVIDER_NAME).strip().lower()


def current_artifact_version(version: str = DEFAULT_VERSION) -> dict[str, str]:
    return artifact_version_dict(build_artifact_version(version, SYSTEM_PROMPT_PATH, TOOLS_PATH))


def provider_model(model: str | None = None) -> str | None:
    provider = make_provider(active_provider_name())
    return model or getattr(provider, "default_model", None)


def get_session(session_id: str) -> ChatSession:
    session = SESSIONS.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Chat session not found.")
    return session


def transcript_path(session: ChatSession) -> Path:
    return TRANSCRIPTS_DIR / f"{session.transcript['transcript_id']}.transcript.json"


def portable_transcript_value(value: Any) -> Any:
    """Replace local project prefixes before values reach the API or transcript."""
    if isinstance(value, dict):
        return {key: portable_transcript_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [portable_transcript_value(item) for item in value]
    if isinstance(value, str):
        root_prefix = f"{ROOT}{os.sep}"
        if value.startswith(root_prefix):
            return value[len(root_prefix):]
    return value


@app.get("/api/config")
def get_config() -> dict[str, Any]:
    artifact = current_artifact_version()
    return {
        "provider": active_provider_name(),
        "model": provider_model(),
        "live_available": live_available(),
        "demo_mode": demo_enabled(),
        "default_history_window": DEFAULT_HISTORY_WINDOW,
        "default_max_tool_rounds": DEFAULT_MAX_TOOL_ROUNDS,
        **artifact,
    }


@app.get("/api/preview")
def get_preview() -> dict[str, Any]:
    import json

    preview = json.loads(PREVIEW_PATH.read_text(encoding="utf-8"))
    return {"is_evidence": False, "transcript": preview}


@app.get("/api/test-cases")
def get_test_cases() -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    datasets: list[dict[str, Any]] = []
    for path in (DATA_DIR / "eval_base.json", DATA_DIR / "eval_group.json"):
        dataset = json.loads(path.read_text(encoding="utf-8"))
        dataset_cases = dataset.get("cases", [])
        datasets.append({
            "dataset_id": dataset.get("dataset_id", path.stem),
            "role": dataset.get("dataset_role"),
            "count": len(dataset_cases),
        })
        for case in dataset_cases:
            prompts = [case["query"]] if case.get("query") else [
                turn["content"] for turn in case.get("turns", []) if turn.get("role") == "user"
            ]
            expected_tools = [
                call.get("name") for call in case.get("expect", {}).get("tool_calls", []) if call.get("name")
            ]
            metadata = case.get("metadata", {})
            cases.append({
                "id": case["id"],
                "suite": case.get("suite"),
                "failure_type": case.get("failure_type"),
                "difficulty": metadata.get("difficulty"),
                "skill": metadata.get("skill"),
                "description": metadata.get("what_it_tests"),
                "prompts": prompts,
                "expected_tools": expected_tools,
            })
    return {"datasets": datasets, "count": len(cases), "cases": cases}


@app.post("/api/sessions", status_code=201)
def create_session(payload: SessionCreate) -> dict[str, Any]:
    if not live_available() and not demo_enabled():
        raise HTTPException(status_code=503, detail=f"API key is not configured for {configured_provider_name()}.")

    created_at = now_iso()
    session_id = uuid4().hex
    session_provider = active_provider_name()
    transcript_id = f"{payload.version}_{session_provider}_{session_id}"
    transcript = {
        "transcript_id": transcript_id,
        **current_artifact_version(payload.version),
        "provider": session_provider,
        "model": provider_model(payload.model),
        "is_evidence": not demo_enabled(),
        "system_prompt": "artifacts/system_prompt.md",
        "tools": "artifacts/tools.yaml",
        "history_window": payload.history_window,
        "max_tool_rounds": payload.max_tool_rounds,
        "created_at": created_at,
        "updated_at": created_at,
        "turns": [],
    }
    with SESSIONS_LOCK:
        SESSIONS[session_id] = ChatSession(transcript=transcript)
    return {"session_id": session_id, "transcript": transcript}


def run_turn(
    session: ChatSession,
    user_text: str,
    event_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    transcript = session.transcript
    system_prompt = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    tool_declarations = load_tool_declarations(TOOLS_PATH)
    tools = to_openai_tools(tool_declarations)
    provider = make_provider(transcript["provider"])

    messages = [
        {"role": "system", "content": system_prompt},
        *trim_history(session.history, transcript["history_window"]),
        {"role": "user", "content": user_text},
    ]
    turn_index = len(transcript["turns"]) + 1
    turn: dict[str, Any] = {
        "turn_index": turn_index,
        "started_at": now_iso(),
        "user": user_text,
        "status": "started",
        "assistant_text": None,
        "rounds": [],
        "tool_events": [],
    }
    if event_callback:
        event_callback({"type": "turn_started", "turn": dict(turn)})
    stream_callback = (
        (lambda event: event_callback(portable_transcript_value(event)))
        if event_callback
        else None
    )

    try:
        result = portable_transcript_value(
            run_model_tool_loop(
                provider=provider,
                messages=messages,
                tools=tools,
                model=transcript["model"],
                max_tool_rounds=transcript["max_tool_rounds"],
                event_callback=stream_callback,
            )
        )
        turn.update(result)
        assistant_text = result["assistant_text"]
        session.history.extend(
            [
                {"role": "user", "content": user_text},
                {"role": "assistant", "content": assistant_text},
            ]
        )
    except Exception as exc:
        turn.update(
            {
                "status": "provider_error",
                "error": f"{type(exc).__name__}: {exc}",
                "assistant_text": "Không thể kết nối tới model provider. Hãy kiểm tra cấu hình và thử lại.",
            }
        )

    turn["ended_at"] = now_iso()
    transcript["turns"].append(turn)
    write_transcript(transcript_path(session), transcript)
    return turn


@app.post("/api/sessions/{session_id}/messages")
async def send_message(session_id: str, payload: MessageCreate) -> dict[str, Any]:
    session = get_session(session_id)
    user_text = payload.message.strip()
    if not user_text:
        raise HTTPException(status_code=422, detail="Message cannot be blank.")

    acquired = session.lock.acquire(blocking=False)
    if not acquired:
        raise HTTPException(status_code=409, detail="This chat session is already processing a message.")
    try:
        turn = await run_in_threadpool(run_turn, session, user_text)
    finally:
        session.lock.release()
    return {"session_id": session_id, "turn": turn}


@app.post("/api/sessions/{session_id}/messages/stream")
async def stream_message(session_id: str, payload: MessageCreate) -> StreamingResponse:
    session = get_session(session_id)
    user_text = payload.message.strip()
    if not user_text:
        raise HTTPException(status_code=422, detail="Message cannot be blank.")
    if not session.lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="This chat session is already processing a message.")

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    def publish(event: dict[str, Any]) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, event)

    def work() -> None:
        try:
            turn = run_turn(session, user_text, publish)
            publish({"type": "turn_finished", "turn": turn})
        except Exception as exc:
            publish({"type": "stream_error", "message": f"{type(exc).__name__}: {exc}"})

    async def event_stream():
        task = asyncio.create_task(run_in_threadpool(work))
        try:
            while True:
                event = await queue.get()
                yield json.dumps(event, ensure_ascii=False, default=str) + "\n"
                if event["type"] in {"turn_finished", "stream_error"}:
                    break
            await task
        finally:
            if not task.done():
                await asyncio.shield(task)
            session.lock.release()

    return StreamingResponse(
        event_stream(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/sessions/{session_id}/transcript")
def get_transcript(session_id: str) -> dict[str, Any]:
    return get_session(session_id).transcript


if (FRONTEND_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="frontend-assets")


@app.get("/{full_path:path}", include_in_schema=False)
def serve_frontend(full_path: str) -> FileResponse:
    index_path = FRONTEND_DIST / "index.html"
    if not index_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Frontend build not found. Run npm install and npm run build in starter_v0/frontend.",
        )
    requested = FRONTEND_DIST / full_path
    if full_path and requested.is_file() and FRONTEND_DIST in requested.resolve().parents:
        return FileResponse(requested)
    return FileResponse(index_path)
