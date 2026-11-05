"""FastAPI REST API endpoints for the Visual Meeting Understanding context service."""

from __future__ import annotations

from typing import Any
from fastapi import APIRouter, FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, Field

from mac_live_translator.context_service.engine import ContextEngine

router = APIRouter()
_global_engine: ContextEngine | None = None


def get_engine() -> ContextEngine:
    global _global_engine
    if _global_engine is None:
        _global_engine = ContextEngine()
    return _global_engine


def set_engine(engine: ContextEngine) -> None:
    global _global_engine
    _global_engine = engine


class CreateSessionRequest(BaseModel):
    session_id: str | None = Field(default=None, max_length=64)


class IngestSegmentRequest(BaseModel):
    segment_id: int = Field(ge=0)
    text: str = Field(min_length=1, max_length=4000)
    is_filler: bool = False


class AnalyzeRequest(BaseModel):
    force: bool = False


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=300)
    top_k: int = Field(default=6, ge=1, le=20)


class CatchupRequest(BaseModel):
    last_read_card_id: int = Field(ge=0)
    page_size: int = Field(default=5, ge=1, le=20)


@router.post("/sessions", status_code=201)
def create_session(req: CreateSessionRequest | None = None) -> dict[str, Any]:
    engine = get_engine()
    sid = req.session_id if req else None
    sess = engine.get_or_create_session(sid or "default")
    return {"session_id": sess.session_id, "generation_id": sess.generation_id, "status": "created"}


@router.post("/sessions/{session_id}/segments")
def ingest_segment(session_id: str, req: IngestSegmentRequest) -> dict[str, Any]:
    engine = get_engine()
    ok = engine.add_segment(session_id, req.segment_id, req.text, req.is_filler)
    return {"session_id": session_id, "segment_id": req.segment_id, "status": "ingested" if ok else "ignored"}


@router.post("/sessions/{session_id}/analyze")
def trigger_analysis(session_id: str, req: AnalyzeRequest | None = None) -> dict[str, Any]:
    """Execute single-pass Claude Haiku analysis. Requires explicit cloud opt-in authorization."""
    engine = get_engine()
    session = engine.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if not engine.cloud_opt_in:
        raise HTTPException(status_code=403, detail="Cloud analysis is disabled. Explicit opt-in required.")

    force = req.force if req else False
    try:
        outcome = engine.trigger_analysis(session_id, force=force)
        if outcome is None:
            return {"session_id": session_id, "status": "skipped", "reason": "cooldown_or_insufficient_batch"}
        result, claim = outcome
        return {
            "session_id": session_id, "generation_id": claim.generation_id,
            "status": "analyzed", "topic": result.topic, "cards_count": len(result.meaning_cards),
            "usage": {"input_tokens": result.usage.input_tokens, "output_tokens": result.usage.output_tokens},
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/sessions/{session_id}/feed")
def get_feed(session_id: str, last_read_card_id: int = Query(default=0, ge=0)) -> dict[str, Any]:
    engine = get_engine()
    feed = engine.get_feed(session_id, last_read_card_id=last_read_card_id)
    if not feed:
        raise HTTPException(status_code=404, detail="Session not found")
    return feed.to_dict()


@router.post("/sessions/{session_id}/search")
def search_transcript(session_id: str, req: SearchRequest) -> dict[str, Any]:
    engine = get_engine()
    results = engine.search_transcript(session_id, req.query, req.top_k)
    return {"session_id": session_id, "query": req.query, "matches": [r.to_dict() for r in results]}


@router.post("/sessions/{session_id}/catchup")
def catchup_session(session_id: str, req: CatchupRequest) -> dict[str, Any]:
    engine = get_engine()
    catchup = engine.get_catchup(session_id, req.last_read_card_id, page_size=req.page_size)
    if not catchup:
        raise HTTPException(status_code=404, detail="Session not found")
    return catchup.to_dict()


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str) -> dict[str, Any]:
    engine = get_engine()
    deleted = engine.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session_id": session_id, "status": "deleted"}


def create_app(engine: ContextEngine | None = None) -> FastAPI:
    """Create a FastAPI application strictly binding to localhost."""
    if engine is not None:
        set_engine(engine)
    app = FastAPI(title="Meeting Understanding Context Service", version="1.1.0")
    app.include_router(router)
    return app
