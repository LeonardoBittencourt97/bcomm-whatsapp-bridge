"""
Pipelines routes — CRM bcomm_inbox
CRUD for sales pipelines, stages, and deal grouping.
"""
import logging
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from services.database import select, insert, update, delete, ensure_supabase

logger = logging.getLogger("bridge")

router = APIRouter(prefix="/crm", tags=["crm"])

PIPELINES_TABLE = "bcomm_inbox.pipelines"
STAGES_TABLE = "bcomm_inbox.stages"
DEALS_TABLE = "bcomm_inbox.deals"


# ── Models ──────────────────────────────────────────────────────

class PipelineCreate(BaseModel):
    name: str
    is_default: Optional[bool] = False
    organization_id: Optional[str] = None


class StageCreate(BaseModel):
    name: str
    position: Optional[int] = 0
    color: Optional[str] = "#3b9eff"


class StageUpdate(BaseModel):
    name: Optional[str] = None
    position: Optional[int] = None
    color: Optional[str] = None


# ── Routes ──────────────────────────────────────────────────────

@router.get("/pipelines")
async def list_pipelines():
    """Lista pipelines com stages aninhados."""
    ensure_supabase()

    pipelines = await select(PIPELINES_TABLE, order="created_at.asc")
    stages = await select(STAGES_TABLE, order="position.asc")

    # Group stages by pipeline_id
    stages_by_pipeline = {}
    for stage in (stages or []):
        pid = stage.get("pipeline_id")
        if pid:
            stages_by_pipeline.setdefault(pid, []).append(stage)

    result = []
    for pipeline in (pipelines or []):
        p = dict(pipeline)
        p["stages"] = stages_by_pipeline.get(p["id"], [])
        result.append(p)

    return {
        "pipelines": result,
        "total": len(result),
    }


@router.get("/pipelines/{pipeline_id}")
async def get_pipeline(pipeline_id: str):
    """Retorna pipeline com deals agrupados por stage."""
    ensure_supabase()

    rows = await select(PIPELINES_TABLE, filters={"id": pipeline_id})
    if not rows:
        raise HTTPException(status_code=404, detail="Pipeline não encontrada")

    pipeline = rows[0]

    # Fetch stages
    stages = await select(
        STAGES_TABLE,
        filters={"pipeline_id": pipeline_id},
        order="position.asc",
    )
    stages = stages or []

    # Fetch deals for this pipeline
    deals = await select(
        DEALS_TABLE,
        filters={"pipeline_id": pipeline_id},
        order="created_at.desc",
    )
    deals = deals or []

    # Group deals by stage
    deals_by_stage = {}
    for deal in deals:
        stage_id = deal.get("stage_id", "")
        deals_by_stage.setdefault(stage_id, []).append(deal)

    # Attach deals to each stage
    for stage in stages:
        stage["deals"] = deals_by_stage.get(stage["id"], [])

    pipeline["stages"] = stages
    pipeline["total_deals"] = len(deals)

    return pipeline


@router.post("/pipelines", status_code=201)
async def create_pipeline(pipeline: PipelineCreate):
    """Cria um novo pipeline."""
    ensure_supabase()

    data = pipeline.model_dump()
    data["created_at"] = datetime.now().isoformat()

    result = await insert(PIPELINES_TABLE, data)
    created = result[0] if isinstance(result, list) else result

    logger.info(f"Pipeline criada: {created.get('id')} ({pipeline.name})")
    return created


@router.post("/pipelines/{pipeline_id}/stages", status_code=201)
async def create_stage(pipeline_id: str, stage: StageCreate):
    """Cria um novo stage dentro de um pipeline."""
    ensure_supabase()

    # Verify pipeline exists
    pipelines = await select(PIPELINES_TABLE, filters={"id": pipeline_id})
    if not pipelines:
        raise HTTPException(status_code=404, detail="Pipeline não encontrada")

    data = stage.model_dump()
    data["pipeline_id"] = pipeline_id
    data["created_at"] = datetime.now().isoformat()

    result = await insert(STAGES_TABLE, data)
    created = result[0] if isinstance(result, list) else result

    logger.info(f"Stage criado: {created.get('id')} ({stage.name}) em pipeline {pipeline_id}")
    return created


@router.put("/stages/{stage_id}")
async def update_stage(stage_id: str, stage: StageUpdate):
    """Atualiza um stage existente."""
    ensure_supabase()

    rows = await select(STAGES_TABLE, filters={"id": stage_id})
    if not rows:
        raise HTTPException(status_code=404, detail="Stage não encontrado")

    data = {k: v for k, v in stage.model_dump().items() if v is not None}
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    await update(STAGES_TABLE, data, filters={"id": stage_id})

    updated = await select(STAGES_TABLE, filters={"id": stage_id})
    logger.info(f"Stage atualizado: {stage_id}")
    return updated[0]


@router.delete("/stages/{stage_id}")
async def delete_stage(stage_id: str):
    """Deleta um stage."""
    ensure_supabase()

    rows = await select(STAGES_TABLE, filters={"id": stage_id})
    if not rows:
        raise HTTPException(status_code=404, detail="Stage não encontrado")

    await delete(STAGES_TABLE, filters={"id": stage_id})
    logger.info(f"Stage deletado: {stage_id}")
    return {"deleted": True, "id": stage_id}
