# ==============================================================
# backend/api.py
# All FastAPI routes and WebSocket endpoint.
# Imports the pipeline and queue worker, wires the queue
# worker's handler to broadcast updates via WebSocket.
# ==============================================================

import os
import json
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from backend.pipeline import Pipeline
from backend.csv_manager import TopicStore
from backend.state import ProjectState, AssetType
from backend.trash_manager import run_startup_cleanup
from backend.queue_worker import worker
from backend.ws_manager import ws_manager

CHANNELS_DIR = os.getenv("CHANNELS_DIR", "channels")

app = FastAPI(title="Video Pipeline")

# Mount static files
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")


# ==============================================================
# Startup
# ==============================================================

@app.on_event("startup")
async def on_startup():
    """Run trash cleanup and start the queue worker on app startup."""
    print("[Startup] Running trash cleanup...")
    run_startup_cleanup(CHANNELS_DIR)

    # Wire queue worker to broadcast all messages via WebSocket
    async def handle_message(message: dict):
        await ws_manager.broadcast(message)

    worker.register_handler(handle_message)
    await worker.start()
    print("[Startup] Queue worker started.")


@app.on_event("shutdown")
async def on_shutdown():
    await worker.stop()


# ==============================================================
# WebSocket
# ==============================================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep connection alive; we only push from server to client
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


# ==============================================================
# Frontend page routes
# ==============================================================

@app.get("/")
async def home():
    return FileResponse("frontend/index.html")

@app.get("/new")
async def new_project_page():
    return FileResponse("frontend/new_project.html")

@app.get("/dashboard")
async def dashboard_page():
    return FileResponse("frontend/dashboard.html")

@app.get("/compile")
async def compile_page():
    return FileResponse("frontend/compile.html")


# ==============================================================
# Channel & topic routes
# ==============================================================

@app.get("/api/channels")
async def list_channels():
    """List all channel names."""
    channels_path = Path(CHANNELS_DIR)
    if not channels_path.exists():
        return JSONResponse([])
    channels = [d.name for d in channels_path.iterdir() if d.is_dir()]
    return JSONResponse(channels)


@app.get("/api/channels/{channel}/topics/available")
async def get_available_topics(channel: str):
    """Return count of available topics for a channel."""
    store = _get_store(channel)
    return JSONResponse({"count": store.count_available()})


@app.get("/api/channels/{channel}/topics/sample")
async def sample_topics(channel: str, n: int = 10):
    """Return a random sample of up to n available topics."""
    store = _get_store(channel)
    return JSONResponse(store.random_sample(n))


@app.get("/api/channels/{channel}/topics/all")
async def all_topics(channel: str):
    """Return all topics for a channel."""
    store = _get_store(channel)
    return JSONResponse(store.get_all())

@app.get("/api/channels/{channel}/niches")
async def get_niches(channel: str):
    """Return sorted list of unique niche values from topics.csv and performance-log."""
    niches = set()

    topics_path = Path(CHANNELS_DIR) / channel / "topics.csv"
    if topics_path.exists():
        store = TopicStore(str(topics_path))
        for t in store.get_all():
            if t.get("niche"):
                niches.add(t["niche"].strip())

    perf_path = Path(CHANNELS_DIR) / channel / "performance-log.csv"
    if perf_path.exists():
        import csv
        with open(perf_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("niche"):
                    niches.add(row["niche"].strip())

    return {"niches": sorted(niches)}


# ==============================================================
# Project list routes
# ==============================================================

@app.get("/api/projects/in-production")
async def list_in_production():
    """Return all in-progress projects across all channels."""
    return JSONResponse(_scan_projects("in-production"))


@app.get("/api/projects/published")
async def list_published():
    """Return all published projects across all channels."""
    return JSONResponse(_scan_projects("published"))


# ==============================================================
# Project creation
# ==============================================================

class NewProjectRequest(BaseModel):
    channel:     str
    title:       str
    niche:       str
    description: str
    format:      str          # "1min" | "2min" | "10min" | "15min"
    topic_id:    Optional[int] = None


@app.post("/api/projects/create")
async def create_project(req: NewProjectRequest):
    """Create a new project directory and state file."""
    pipeline = Pipeline.create(
        channel=req.channel,
        title=req.title,
        niche=req.niche,
        description=req.description,
        format=req.format,
        topic_id=req.topic_id
    )
    return JSONResponse({
        "project_id":  pipeline.project_id,
        "project_dir": pipeline.project_dir
    })


# ==============================================================
# Script routes
# ==============================================================

@app.post("/api/projects/{channel}/{project_id}/script/generate")
async def generate_script(channel: str, project_id: str):
    """Trigger script generation for a project."""
    import asyncio
    pipeline = Pipeline(channel, project_id)
    asyncio.create_task(pipeline.generate_script())
    return JSONResponse({"status": "generating"})


class ApproveScriptRequest(BaseModel):
    final_script: str
    tags:         list
    shot_list:    list
    full_approve: bool = False


@app.post("/api/projects/{channel}/{project_id}/script/approve")
async def approve_script(channel: str, project_id: str,
                          req: ApproveScriptRequest):
    """Approve the final script and kick off asset generation."""
    import asyncio
    pipeline = Pipeline(channel, project_id)
    asyncio.create_task(pipeline.approve_script(
        final_script=req.final_script,
        tags=req.tags,
        shot_list=req.shot_list,
        full_approve=req.full_approve
    ))
    return JSONResponse({"status": "approved"})


# ==============================================================
# Asset routes
# ==============================================================

@app.post("/api/projects/{channel}/{project_id}/assets/{asset_id}/approve")
async def approve_asset(channel: str, project_id: str, asset_id: int):
    import asyncio
    pipeline = Pipeline(channel, project_id)
    asyncio.create_task(pipeline.approve_asset(asset_id))
    return JSONResponse({"status": "approved"})


@app.post("/api/projects/{channel}/{project_id}/assets/{asset_id}/reject")
async def reject_asset(channel: str, project_id: str, asset_id: int,
                        note: str = ""):
    import asyncio
    pipeline = Pipeline(channel, project_id)
    asyncio.create_task(pipeline.reject_asset(asset_id, note))
    return JSONResponse({"status": "rejected"})


class RetryRequest(BaseModel):
    new_prompt: Optional[str] = None


@app.post("/api/projects/{channel}/{project_id}/assets/{asset_id}/retry")
async def retry_asset(channel: str, project_id: str, asset_id: int,
                       req: RetryRequest):
    import asyncio
    pipeline = Pipeline(channel, project_id)
    asyncio.create_task(pipeline.retry_asset(asset_id, req.new_prompt))
    return JSONResponse({"status": "retrying"})


@app.post("/api/projects/{channel}/{project_id}/assets/{asset_id}/freeze")
async def freeze_asset(channel: str, project_id: str, asset_id: int):
    import asyncio
    pipeline = Pipeline(channel, project_id)
    asyncio.create_task(pipeline.freeze_asset(asset_id))
    return JSONResponse({"status": "frozen"})


@app.post("/api/projects/{channel}/{project_id}/assets/{asset_id}/thumbnail")
async def promote_thumbnail(channel: str, project_id: str, asset_id: int):
    import asyncio
    pipeline = Pipeline(channel, project_id)
    asyncio.create_task(pipeline.promote_to_thumbnail(asset_id))
    return JSONResponse({"status": "promoted"})


class AddAssetRequest(BaseModel):
    asset_type: str
    prompt:     str


@app.post("/api/projects/{channel}/{project_id}/assets/add")
async def add_asset(channel: str, project_id: str, req: AddAssetRequest):
    import asyncio
    pipeline = Pipeline(channel, project_id)
    asyncio.create_task(pipeline.add_manual_asset(req.asset_type, req.prompt))
    return JSONResponse({"status": "dispatched"})

@app.post("/api/projects/{channel}/{project_id}/resume")
async def resume_project(channel: str, project_id: str):
    """Re-dispatch any assets stuck in pending state after a server restart."""
    pipeline = Pipeline(channel, project_id)
    ps = pipeline._load()
    requeued = 0
    for asset in ps.get("assets") or []:
        if asset["state"] in ("pending", "generating"):
            ps.update_asset(asset["asset_id"], state="waiting")
            requeued += 1
    return {"requeued": requeued}

# ==============================================================
# Project state route (for UI restore)
# ==============================================================

@app.get("/api/projects/{channel}/{project_id}/state")
async def get_project_state(channel: str, project_id: str):
    """Return the full project state for UI restore."""
    project_dir = str(
        Path(CHANNELS_DIR) / channel / "in-production" / project_id
    )
    try:
        ps = ProjectState.load(project_dir)
        return JSONResponse(ps.data)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found")


# ==============================================================
# Asset file serving
# ==============================================================

@app.get("/api/projects/{channel}/{project_id}/assets/file/{filename}")
async def serve_asset(channel: str, project_id: str, filename: str):
    """Serve a generated asset file to the browser for preview."""
    asset_path = (
        Path(CHANNELS_DIR) / channel / "in-production"
        / project_id / "assets" / filename
    )
    if not asset_path.exists():
        raise HTTPException(status_code=404, detail="Asset file not found")
    return FileResponse(str(asset_path))


# ==============================================================
# Compile & publish routes
# ==============================================================

@app.post("/api/projects/{channel}/{project_id}/compile")
async def compile_project(channel: str, project_id: str):
    import asyncio
    pipeline = Pipeline(channel, project_id)
    asyncio.create_task(pipeline.compile())
    return JSONResponse({"status": "compiling"})


class PublishRequest(BaseModel):
    video_url: str


@app.post("/api/projects/{channel}/{project_id}/publish")
async def publish_project(channel: str, project_id: str,
                           req: PublishRequest):
    import asyncio
    pipeline = Pipeline(channel, project_id)
    asyncio.create_task(pipeline.mark_published(req.video_url))
    return JSONResponse({"status": "published"})


# ==============================================================
# Connector health checks
# ==============================================================

@app.get("/api/health")
async def health_check():
    """Check which AI connectors are reachable."""
    from backend.connectors.flux import is_available as flux_ok
    from backend.connectors.kling import is_available as kling_ok
    from backend.connectors.elevenlabs import is_available as el_ok
    from backend.connectors.suno import is_available as suno_ok

    return JSONResponse({
        "flux":       await flux_ok(),
        "kling":      await kling_ok(),
        "elevenlabs": await el_ok(),
        "suno":       await suno_ok(),
    })


# ==============================================================
# Internal helpers
# ==============================================================

def _get_store(channel: str) -> TopicStore:
    csv_path = str(Path(CHANNELS_DIR) / channel / "topics.csv")
    if not Path(csv_path).exists():
        raise HTTPException(
            status_code=404,
            detail=f"Channel '{channel}' not found"
        )
    return TopicStore(csv_path)


def _scan_projects(subfolder: str) -> list:
    """
    Walk all channels and return a list of project state summaries
    from the given subfolder (in-production or published).
    """
    results = []
    channels_path = Path(CHANNELS_DIR)
    if not channels_path.exists():
        return results

    for channel_dir in channels_path.iterdir():
        if not channel_dir.is_dir():
            continue
        target = channel_dir / subfolder
        if not target.exists():
            continue
        for project_dir in target.iterdir():
            if not project_dir.is_dir():
                continue
            state_file = project_dir / "project_state.json"
            if state_file.exists():
                try:
                    with open(state_file, "r", encoding="utf-8") as f:
                        state = json.load(f)
                    results.append({
                        "project_id":  state.get("project_id"),
                        "title":       state.get("title"),
                        "niche":       state.get("niche"),
                        "description": state.get("description"),
                        "format":      state.get("format"),
                        "channel":     state.get("channel"),
                        "created_at":  state.get("created_at"),
                        "updated_at":  state.get("updated_at"),
                        "current_page": state.get("current_page"),
                        "exported":    state.get("exported"),
                        "video_url":   state.get("video_url", ""),
                        "asset_counts": _count_assets(state.get("assets", []))
                    })
                except Exception as e:
                    print(f"[API] Could not read state for {project_dir.name}: {e}")
    return results


def _count_assets(assets: list) -> dict:
    """Return a count of assets grouped by state for the UI summary."""
    counts = {}
    for asset in assets:
        state = asset.get("state", "unknown")
        counts[state] = counts.get(state, 0) + 1
    return counts

class AddTopicRequest(BaseModel):
    name: str
    niche: str
    description: str = ""

@app.post("/api/channels/{channel}/topics/add")
async def add_topic(channel: str, req: AddTopicRequest):
    store = _get_store(channel)
    topic = store.add_topic(req.name, req.niche, req.description)
    return JSONResponse(topic)
    