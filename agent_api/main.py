"""
Servidor FastAPI – API del agente analítico BI.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from agent_api.core.dashboard_service import (
    create_dashboard_entry,
    delete_dashboard_entry,
    get_dashboard_entries,
    is_dax_in_dashboard,
    refresh_all_dashboard_entries,
    refresh_dashboard_entry,
)
from agent_api.core.debug_log import is_debug_enabled
from agent_api.core.graph import run_agent
from agent_api.core.security import get_allowed_cube_address, validate_question

_ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(_ENV_PATH)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent_api")

REQUEST_TIMEOUT_SEC = int(os.getenv("AGENT_REQUEST_TIMEOUT_SEC", "90"))


class QueryRequest(BaseModel):
    cube_address: str | None = Field(default=None, max_length=500)
    question: str = Field(..., min_length=1, max_length=500)


class DebugLogEntry(BaseModel):
    step: str
    message: str
    level: str = "info"
    elapsed_ms: int = 0


class QueryResponse(BaseModel):
    text_response: str
    dax_query: str
    echarts_config: dict[str, Any]
    debug_log: list[DebugLogEntry] = Field(default_factory=list)
    elapsed_ms: int = 0


class DashboardAddRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    question: str = Field(default="", max_length=500)
    dax_query: str = Field(..., min_length=8, max_length=4000)
    cube_address: str | None = Field(default=None, max_length=500)


class DashboardEntryResponse(BaseModel):
    id: str
    title: str
    question: str
    dax_query: str
    chartConfig: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None
    last_refresh_at: str | None = None
    last_error: str | None = None
    elapsed_ms: int = 0
    row_count: int = 0


class DashboardListResponse(BaseModel):
    items: list[DashboardEntryResponse]
    count: int


class DashboardCheckResponse(BaseModel):
    included: bool
    item_id: str | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not os.getenv("DEEPSEEK_API_KEY"):
        raise RuntimeError("DEEPSEEK_API_KEY no está configurada. Revise su archivo .env")
    yield


app = FastAPI(
    title="Agent API – BI Analytics",
    description="Agente inteligente para consultas DAX sobre cubos Tabular SSAS",
    version="1.0.0",
    lifespan=lifespan,
)

cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in cors_origins],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/query", response_model=QueryResponse)
async def query_cube(payload: QueryRequest) -> QueryResponse:
    t0 = time.perf_counter()
    logger.info("Query recibida: %s", payload.question[:80])

    try:
        question = validate_question(payload.question)
        cube_address = get_allowed_cube_address(payload.cube_address)

        result = await asyncio.wait_for(
            asyncio.to_thread(run_agent, question, cube_address),
            timeout=REQUEST_TIMEOUT_SEC,
        )

        elapsed = int((time.perf_counter() - t0) * 1000)
        debug_log = result.get("debug_log", []) if is_debug_enabled() else []

        response = QueryResponse(
            text_response=result["text_response"],
            dax_query=result["dax_query"],
            echarts_config=result["echarts_config"],
            debug_log=debug_log,
            elapsed_ms=elapsed,
        )

        logger.info(
            "Query completada en %dms | text=%d chars | chart=%s | enviando respuesta HTTP",
            elapsed,
            len(result.get("text_response", "")),
            bool(result.get("echarts_config", {}).get("series")),
        )

        return response
    except asyncio.TimeoutError as exc:
        elapsed = int((time.perf_counter() - t0) * 1000)
        logger.error("Timeout después de %dms", elapsed)
        raise HTTPException(
            status_code=504,
            detail=f"La consulta superó el tiempo límite de {REQUEST_TIMEOUT_SEC}s.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Error en query_cube")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/v1/dashboard", response_model=DashboardListResponse)
async def list_dashboard(
    cube_address: str | None = Query(default=None),
) -> DashboardListResponse:
    try:
        entries = await asyncio.to_thread(get_dashboard_entries, cube_address)
        items = [DashboardEntryResponse(**entry) for entry in entries]
        return DashboardListResponse(items=items, count=len(items))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Error listando dashboard")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/v1/dashboard", response_model=DashboardEntryResponse)
async def add_dashboard_item(payload: DashboardAddRequest) -> DashboardEntryResponse:
    try:
        entry = await asyncio.to_thread(
            create_dashboard_entry,
            title=payload.title,
            question=payload.question,
            dax_query=payload.dax_query,
            cube_address=payload.cube_address,
        )
        return DashboardEntryResponse(**entry)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Error agregando al dashboard")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.delete("/api/v1/dashboard/{item_id}")
async def remove_dashboard_item(item_id: str) -> dict[str, bool]:
    removed = await asyncio.to_thread(delete_dashboard_entry, item_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Indicador no encontrado en el dashboard.")
    return {"ok": True}


@app.post("/api/v1/dashboard/{item_id}/refresh", response_model=DashboardEntryResponse)
async def refresh_dashboard_item(
    item_id: str,
    cube_address: str | None = Query(default=None),
) -> DashboardEntryResponse:
    try:
        entry = await asyncio.to_thread(refresh_dashboard_entry, item_id, cube_address)
        return DashboardEntryResponse(**entry)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Error refrescando indicador %s", item_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/v1/dashboard/refresh-all", response_model=DashboardListResponse)
async def refresh_all_dashboard(
    cube_address: str | None = Query(default=None),
) -> DashboardListResponse:
    try:
        entries = await asyncio.to_thread(refresh_all_dashboard_entries, cube_address)
        items = [DashboardEntryResponse(**entry) for entry in entries]
        return DashboardListResponse(items=items, count=len(items))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Error refrescando dashboard completo")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/v1/dashboard/check", response_model=DashboardCheckResponse)
async def check_dashboard_dax(
    dax_query: str = Query(..., min_length=8),
) -> DashboardCheckResponse:
    item = await asyncio.to_thread(is_dax_in_dashboard, dax_query)
    if item:
        return DashboardCheckResponse(included=True, item_id=item["id"])
    return DashboardCheckResponse(included=False, item_id=None)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "agent_api.main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=True,
    )
