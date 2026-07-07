"""Debug API routes for Phase introspection and replay."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

debug_router = APIRouter(prefix="/debug", tags=["debug"])

# In-memory breakpoint store (per-session)
_breakpoints: dict[str, dict[str, Any]] = {}


@debug_router.get("/runs/{run_id}/trace")
async def get_run_trace(run_id: str) -> dict[str, Any]:
    """Get the full trace tree for a run."""
    return {"run_id": run_id, "status": "not_implemented"}


@debug_router.get("/runs/{run_id}/phases/{phase_name}/trace")
async def get_phase_trace(run_id: str, phase_name: str) -> dict[str, Any]:
    """Get detailed trace for a single phase execution."""
    return {"run_id": run_id, "phase_name": phase_name, "status": "not_implemented"}


@debug_router.post("/phases/{phase_name}/dry-run")
async def dry_run_phase(phase_name: str, body: dict[str, Any]) -> dict[str, Any]:
    """Execute a phase without persisting to store (dry-run)."""
    valid_phases = {"planning", "knowledge_retrieval", "evidence_acquisition", "evidence_extraction", "synthesis", "knowledge_upsert"}
    if phase_name not in valid_phases:
        raise HTTPException(400, f"Unknown phase: {phase_name}")
    return {
        "phase_name": phase_name,
        "dry_run": True,
        "input": body,
        "status": "not_implemented",
    }


@debug_router.post("/runs/{run_id}/phases/{phase_name}/replay")
async def replay_phase(run_id: str, phase_name: str) -> dict[str, Any]:
    """Re-execute a phase using its original inputs."""
    return {
        "run_id": run_id,
        "phase_name": phase_name,
        "replay": True,
        "status": "not_implemented",
    }


@debug_router.post("/runs/{run_id}/breakpoints")
async def set_breakpoint(run_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Set a breakpoint before a specific phase."""
    phase = body.get("phase", "")
    bp_id = f"{run_id}:{phase}"
    _breakpoints[bp_id] = {"run_id": run_id, "phase": phase, "active": True}
    return {"breakpoint_id": bp_id, "active": True}


@debug_router.post("/runs/{run_id}/breakpoints/resume")
async def resume_breakpoint(run_id: str) -> dict[str, Any]:
    """Resume execution after a breakpoint."""
    for bp_id, bp in list(_breakpoints.items()):
        if bp["run_id"] == run_id:
            _breakpoints.pop(bp_id)
    return {"run_id": run_id, "resumed": True}


@debug_router.get("/runs/{run_id}/llm-calls")
async def list_llm_calls(run_id: str) -> dict[str, Any]:
    """List all LLM calls for a run."""
    return {"run_id": run_id, "calls": []}


@debug_router.get("/runs/{run_id}/tool-calls")
async def list_tool_calls(run_id: str) -> dict[str, Any]:
    """List all tool calls for a run."""
    return {"run_id": run_id, "calls": []}
