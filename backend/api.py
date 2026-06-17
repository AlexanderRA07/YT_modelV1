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
from backend.csv_manager import TopicStore, TopicStatus
from backend.draft_manager import DraftStore
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

@app.get("/delete")
async def delete_page():
    return FileResponse("frontend/delete.html")

@app.get("/log-new")
async def log_new_page():
    return FileResponse("frontend/log_new.html")


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
    in_prod = _in_production_topic_ids()
    available = [t for t in store.get_available() if int(t["id"]) not in in_prod]
    return JSONResponse({"count": len(available)})


@app.get("/api/channels/{channel}/topics/sample")
async def sample_topics(channel: str, n: int = 10):
    """Return a random sample of up to n available topics."""
    store = _get_store(channel)
    in_prod = _in_production_topic_ids()
    available = [t for t in store.get_available() if int(t["id"]) not in in_prod]
    import random
    return JSONResponse(random.sample(available, min(n, len(available))))


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
# Project deletion
# ==============================================================

@app.delete("/api/projects/{channel}/{project_id}")
async def delete_project(channel: str, project_id: str):
    """
    Permanently delete an in-production project directory.
    If the project has a linked topic_id, resets its CSV status back to 'idea'
    so the topic surfaces again as available.
    """
    import shutil
    project_dir = Path(CHANNELS_DIR) / channel / "in-production" / project_id

    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="Project not found")

    state_file = project_dir / "project_state.json"
    if state_file.exists():
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                state = json.load(f)
            topic_id = state.get("topic_id")
            if topic_id is not None:
                csv_path = Path(CHANNELS_DIR) / channel / "topics.csv"
                if csv_path.exists():
                    TopicStore(str(csv_path)).update_status(int(topic_id), TopicStatus.IDEA)
        except Exception as e:
            print(f"[API] Could not reset topic status during delete: {e}")

    shutil.rmtree(project_dir)
    return JSONResponse({"status": "deleted"})


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
    references:  str = ""     # semicolon-separated source URLs
    concepts:    str = ""     # creative directions from CSV


@app.post("/api/projects/create")
async def create_project(req: NewProjectRequest):
    """Create a new project directory and state file."""
    pipeline = Pipeline.create(
        channel=req.channel,
        title=req.title,
        niche=req.niche,
        description=req.description,
        format=req.format,
        topic_id=req.topic_id,
        references=req.references,
        concepts=req.concepts
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
    description:  str  = ""
    credits:      str  = ""


@app.post("/api/projects/{channel}/{project_id}/script/approve")
async def approve_script(channel: str, project_id: str,
                         req: ApproveScriptRequest):
    """Approve the final script and kick off asset generation."""
    import asyncio
    from backend.connectors.claude import extract_shot_list as _extract_shots
    shot_list = await _extract_shots(req.final_script)
    pipeline = Pipeline(channel, project_id)
    asyncio.create_task(pipeline.approve_script(
        final_script=req.final_script,
        tags=req.tags,
        shot_list=shot_list,
        full_approve=req.full_approve,
        description=req.description,
        credits=req.credits
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
                        "topic_id":    state.get("topic_id"),
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


def _in_production_topic_ids() -> set[int]:
    """
    Scan all in-production project_state.json files and return the set of
    topic_ids that are already being worked on.  Used to prevent a CSV topic
    from surfacing as 'available' when its project directory already exists,
    even if the CSV status was never flipped (e.g. crash between directory
    creation and CSV write).
    """
    topic_ids: set[int] = set()
    channels_path = Path(CHANNELS_DIR)
    if not channels_path.exists():
        return topic_ids
    for channel_dir in channels_path.iterdir():
        if not channel_dir.is_dir():
            continue
        for project_dir in (channel_dir / "in-production").glob("*/"):
            state_file = project_dir / "project_state.json"
            if not state_file.exists():
                continue
            try:
                with open(state_file, "r", encoding="utf-8") as f:
                    state = json.load(f)
                tid = state.get("topic_id")
                if tid is not None:
                    topic_ids.add(int(tid))
            except Exception:
                pass
    return topic_ids

class AddTopicRequest(BaseModel):
    name:        str
    niche:       str
    description: str = ""
    format:      str = ""
    references:  str = ""
    concepts:    str = ""

@app.post("/api/channels/{channel}/topics/add")
async def add_topic(channel: str, req: AddTopicRequest):
    store = _get_store(channel)
    topic = store.add_topic(
        req.name, req.niche, req.description,
        format=req.format, references=req.references, concepts=req.concepts
    )
    return JSONResponse(topic)


class UpdateTopicRequest(BaseModel):
    name:        Optional[str] = None
    niche:       Optional[str] = None
    description: Optional[str] = None
    format:      Optional[str] = None
    references:  Optional[str] = None
    concepts:    Optional[str] = None

@app.patch("/api/channels/{channel}/topics/{topic_id}")
async def update_topic(channel: str, topic_id: int, req: UpdateTopicRequest):
    """Update editable fields on an existing topic."""
    store = _get_store(channel)
    updates = {k: v for k, v in req.dict().items() if v is not None}
    topic = store.update_topic(topic_id, **updates)
    if topic is None:
        raise HTTPException(status_code=404, detail=f"Topic {topic_id} not found")
    return JSONResponse(topic)


# ==============================================================
# Draft routes
# ==============================================================

def _get_draft_store(channel: str) -> DraftStore:
    channel_dir = Path(CHANNELS_DIR) / channel
    if not channel_dir.exists():
        raise HTTPException(status_code=404, detail=f"Channel '{channel}' not found")
    return DraftStore(str(channel_dir / "drafts.json"))


class DraftRequest(BaseModel):
    name:        str = ""
    niche:       str = ""
    description: str = ""
    format:      str = ""
    references:  str = ""
    concepts:    str = ""


@app.get("/api/channels/{channel}/drafts")
async def list_drafts(channel: str):
    return JSONResponse(_get_draft_store(channel).get_all())


@app.post("/api/channels/{channel}/drafts")
async def create_draft(channel: str, req: DraftRequest):
    draft = _get_draft_store(channel).create(**req.dict())
    return JSONResponse(draft)


@app.put("/api/channels/{channel}/drafts/{draft_id}")
async def update_draft(channel: str, draft_id: str, req: DraftRequest):
    draft = _get_draft_store(channel).update(draft_id, **req.dict())
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    return JSONResponse(draft)


@app.delete("/api/channels/{channel}/drafts/{draft_id}")
async def delete_draft(channel: str, draft_id: str):
    ok = _get_draft_store(channel).delete(draft_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Draft not found")
    return JSONResponse({"status": "deleted"})


@app.post("/api/channels/{channel}/drafts/{draft_id}/submit")
async def submit_draft(channel: str, draft_id: str):
    """Validate a draft and write it as a new CSV entry, then delete the draft."""
    draft_store = _get_draft_store(channel)
    draft = draft_store.get_by_id(draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    missing = [f for f in ("name", "niche", "description") if not draft.get(f, "").strip()]
    if missing:
        raise HTTPException(status_code=422, detail=f"Missing required fields: {', '.join(missing)}")
    topic_store = _get_store(channel)
    topic = topic_store.add_topic(
        draft["name"], draft["niche"], draft["description"],
        format=draft.get("format", ""),
        references=draft.get("references", ""),
        concepts=draft.get("concepts", ""),
    )
    draft_store.delete(draft_id)
    return JSONResponse(topic)
