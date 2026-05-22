# ==============================================================
# backend/pipeline.py
# Pipeline orchestrator.
# Coordinates all stages of production for a single project:
#   1. Project initialization
#   2. Script generation
#   3. Asset generation (parallel, queue-safe)
#   4. Compilation trigger
#
# All connector calls go through retry.py.
# All state mutations go through state.py.
# All UI updates go through queue_worker.py.
# ==============================================================

import asyncio
import os
from pathlib import Path
from datetime import datetime
from typing import Optional

from backend.state import (
    ProjectState, AssetState, AssetType, AppPage, new_asset
)
from backend.csv_manager import TopicStore, TopicStatus
from backend.trash_manager import TrashManager
from backend.retry import with_retry
from backend.asset_targets import get_all_targets, get_compile_minimums
from backend.queue_worker import (
    worker,
    asset_state_msg, asset_returned_msg, asset_error_msg,
    project_error_msg, compile_ready_msg, status_msg, retry_notice_msg
)

# Connectors (imported lazily inside methods so missing keys don't crash startup)
# from backend.connectors.claude import generate_script
# from backend.connectors.flux import generate_image
# from backend.connectors.kling import generate_animation
# from backend.connectors.elevenlabs import generate_voice
# from backend.connectors.suno import generate_music

CHANNELS_DIR = os.getenv("CHANNELS_DIR", "channels")


# ==============================================================
# Helpers
# ==============================================================

def _project_dir(channel: str, project_id: str) -> str:
    return str(Path(CHANNELS_DIR) / channel / "in-production" / project_id)

def _assets_dir(project_dir: str) -> str:
    path = Path(project_dir) / "assets"
    path.mkdir(parents=True, exist_ok=True)
    return str(path)

def _prompt_filename(asset_id: int, asset_type: str) -> str:
    """Return the prompt filename for a given asset."""
    prefix = {
        AssetType.IMAGE:     "prompt",
        AssetType.ANIMATION: "prompt",
        AssetType.VOICE:     "prompt_voice",
        AssetType.MUSIC:     "prompt_music",
        AssetType.THUMBNAIL: "prompt_thumb",
    }.get(asset_type, "prompt")
    suffix = {
        AssetType.ANIMATION: "_anim",
    }.get(asset_type, "")
    return f"{prefix}{asset_id}{suffix}.txt"

def _asset_filename(asset_id: int, asset_type: str) -> str:
    """Return the asset filename for a given asset."""
    ext = {
        AssetType.IMAGE:     "jpg",
        AssetType.ANIMATION: "mp4",
        AssetType.VOICE:     "mp3",
        AssetType.MUSIC:     "mp3",
        AssetType.THUMBNAIL: "jpg",
    }.get(asset_type, "bin")
    prefix = {
        AssetType.IMAGE:     "image",
        AssetType.ANIMATION: "animation",
        AssetType.VOICE:     "voice",
        AssetType.MUSIC:     "music",
        AssetType.THUMBNAIL: "thumb",
    }.get(asset_type, "asset")
    return f"{prefix}{asset_id}.{ext}"

def _save_prompt(assets_dir: str, asset_id: int,
                 asset_type: str, prompt: str):
    """Write prompt text to its numbered .txt file."""
    filename = _prompt_filename(asset_id, asset_type)
    path = Path(assets_dir) / filename
    with open(path, "w", encoding="utf-8") as f:
        f.write(prompt)


# ==============================================================
# Pipeline class
# ==============================================================

class Pipeline:
    """
    Manages the full production lifecycle of a single project.

    Usage (from FastAPI endpoints):
        pipeline = Pipeline(channel="my-channel", project_id="2024-01_black-holes")
        await pipeline.start_new(topic_id=5, format="10min")
        await pipeline.approve_script(final_script, tags, shot_list)
        # asset generation then runs in background tasks
    """

    def __init__(self, channel: str, project_id: str):
        self.channel = channel
        self.project_id = project_id
        self.project_dir = _project_dir(channel, project_id)
        self._ps: Optional[ProjectState] = None
        self._trash: Optional[TrashManager] = None

    # ----------------------------------------------------------
    # Load state
    # ----------------------------------------------------------
    def _load(self) -> ProjectState:
        if self._ps is None:
            self._ps = ProjectState.load(self.project_dir)
        return self._ps

    def _get_trash(self) -> TrashManager:
        if self._trash is None:
            self._trash = TrashManager(self.project_dir)
        return self._trash

    # ----------------------------------------------------------
    # STAGE 1 -- Project initialization
    # ----------------------------------------------------------
    @classmethod
    def create(cls, channel: str, title: str, niche: str,
               description: str, format: str,
               topic_id: Optional[int] = None) -> "Pipeline":
        """
        Create a new project directory and state file.
        Marks the CSV topic as in_production if topic_id is provided.
        Returns a ready Pipeline instance.
        """
        # Build a filesystem-safe project_id from date + title
        safe_title = "".join(
            c if c.isalnum() or c in "-_" else "_"
            for c in title.lower().replace(" ", "-")
        )[:40]
        project_id = f"{datetime.now().strftime('%Y-%m')}_{safe_title}"
        project_dir = _project_dir(channel, project_id)

        # Create directories
        Path(project_dir).mkdir(parents=True, exist_ok=True)
        (Path(project_dir) / "assets").mkdir(exist_ok=True)
        (Path(project_dir) / "trash").mkdir(exist_ok=True)
        (Path(project_dir) / "export").mkdir(exist_ok=True)

        # Create initial state
        ProjectState.create(
            project_dir=project_dir,
            project_id=project_id,
            title=title,
            niche=niche,
            description=description,
            format=format,
            channel=channel
        )

        # Mark topic in CSV
        if topic_id is not None:
            csv_path = str(
                Path(CHANNELS_DIR) / channel / "topics.csv"
            )
            store = TopicStore(csv_path)
            store.mark_in_production(topic_id)

        return cls(channel, project_id)

    # ----------------------------------------------------------
    # STAGE 2 -- Script generation
    # ----------------------------------------------------------
    async def generate_script(self) -> dict:
        """
        Call the Claude connector to generate a script draft.
        Returns the result dict (ok, data, error).
        Posts status updates to the queue.
        """
        from backend.connectors.claude import generate_script as _gen

        ps = self._load()
        await worker.post(status_msg("Generating script..."))
        ps.update_ui(AppPage.SCRIPT_REVIEW)

        async def call():
            style_guide_path = Path(CHANNELS_DIR) / self.channel / "style_guide.md"
            style_guide = ""
            if style_guide_path.exists():
                style_guide = style_guide_path.read_text(encoding="utf-8")

            return await _gen(
                title=ps.get("title"),
                description=ps.get("description"),
                niche=ps.get("niche"),
                format=ps.get("format"),
                style_guide=style_guide
            )

        result = await with_retry(
            fn=call,
            module="claude",
            on_retry=lambda attempt, err: worker.post(
                status_msg(f"Script generation retry {attempt}/{5}: {err}")
            )
        )

        if result["ok"]:
            draft = result["data"]["script"]
            tags  = result["data"].get("tags", [])
            ps.update_script(draft=draft, tags=tags)
            await worker.post(status_msg("Script ready for review."))
        else:
            ps.add_error("claude", result["error"]["detail"])
            await worker.post(project_error_msg(
                "claude", result["error"]["detail"]
            ))

        return result

    async def approve_script(self, final_script: str, tags: list,
                              shot_list: list, full_approve: bool = False):
        """
        Called when user approves the script (either Approve or Full Approve).
        Saves final script, updates flags, then dispatches initial asset generation.
        """
        ps = self._load()
        ps.update_script(final=final_script, tags=tags, shot_list=shot_list)
        ps.update("script_approved", True)
        ps.update("full_approve", full_approve)
        ps.update_ui(AppPage.DASHBOARD)
        await worker.post(status_msg("Script approved. Dispatching asset generation..."))
        await self._dispatch_initial_assets()

    # ----------------------------------------------------------
    # STAGE 3 -- Asset dispatch
    # ----------------------------------------------------------
    async def _dispatch_initial_assets(self):
        """
        Dispatch the initial batch of generation jobs based on format targets.
        Images, voice, music, and thumbnails are dispatched immediately.
        Animations are dispatched only after their image is approved.
        """
        ps = self._load()
        targets = get_all_targets(ps.get("format"))
        shot_list = ps.get("script")["shot_list"]

        tasks = []

        # Images
        for i in range(targets["image"]):
            prompt = shot_list[i]["image_prompt"] if i < len(shot_list) else f"Scene {i+1}"
            asset_id = ps.next_asset_id()
            ps.add_asset(new_asset(asset_id, AssetType.IMAGE, prompt))
            tasks.append(self._generate_asset(asset_id, AssetType.IMAGE, prompt))

        # Thumbnails
        for i in range(targets["thumbnail"]):
            prompt = f"Thumbnail for: {ps.get('title')} (variant {i+1})"
            asset_id = ps.next_asset_id()
            ps.add_asset(new_asset(asset_id, AssetType.THUMBNAIL, prompt))
            tasks.append(self._generate_asset(asset_id, AssetType.THUMBNAIL, prompt))

        # Voice
        voice_prompt = ps.get("script")["final"]
        asset_id = ps.next_asset_id()
        ps.add_asset(new_asset(asset_id, AssetType.VOICE, voice_prompt))
        tasks.append(self._generate_asset(asset_id, AssetType.VOICE, voice_prompt))

        # Music
        music_prompt = f"Background music for a {ps.get('niche')} video: {ps.get('title')}"
        asset_id = ps.next_asset_id()
        ps.add_asset(new_asset(asset_id, AssetType.MUSIC, music_prompt))
        tasks.append(self._generate_asset(asset_id, AssetType.MUSIC, music_prompt))

        # Run all in parallel
        await asyncio.gather(*tasks)

    async def _generate_asset(self, asset_id: int,
                               asset_type: str, prompt: str):
        """
        Dispatch a single asset generation job.
        Saves the prompt file, calls the appropriate connector via retry,
        posts result to the queue, and updates project state.
        """
        ps = self._load()
        assets_dir = _assets_dir(self.project_dir)
        _save_prompt(assets_dir, asset_id, asset_type, prompt)

        # Mark as pending
        ps.update_asset(asset_id, state=AssetState.PENDING)
        await worker.post(asset_state_msg(asset_id, asset_type, AssetState.PENDING))

        # Select connector
        connector_fn = self._get_connector(asset_type)

        async def call():
            return await connector_fn(prompt=prompt, asset_id=asset_id)

        async def on_retry(attempt: int, err: str):
            await worker.post(retry_notice_msg(asset_id, asset_type, attempt, err))

        result = await with_retry(
            fn=call,
            module=asset_type,
            asset_id=asset_id,
            on_retry=on_retry
        )

        if result["ok"]:
            filename = result["data"]["filename"]
            ps.update_asset(
                asset_id,
                state=AssetState.REVIEW,
                filename=filename,
                retry_count=0
            )
            await worker.post(
                asset_returned_msg(asset_id, asset_type, filename, prompt)
            )
            # Check if compile thresholds are now met
            await self._check_compile_ready()
        else:
            error_detail = result["error"]["detail"]
            ps.update_asset(
                asset_id,
                state=AssetState.ERROR,
                error_detail=error_detail
            )
            ps.add_error(asset_type, error_detail, asset_id)
            await worker.post(asset_error_msg(asset_id, asset_type, error_detail))
            await worker.post(project_error_msg(asset_type, error_detail, asset_id))

    def _get_connector(self, asset_type: str):
        """Return the appropriate async connector function for an asset type."""
        if asset_type == AssetType.IMAGE:
            from backend.connectors.flux import generate_image
            return generate_image
        elif asset_type == AssetType.ANIMATION:
            from backend.connectors.kling import generate_animation
            return generate_animation
        elif asset_type == AssetType.VOICE:
            from backend.connectors.elevenlabs import generate_voice
            return generate_voice
        elif asset_type == AssetType.MUSIC:
            from backend.connectors.suno import generate_music
            return generate_music
        elif asset_type == AssetType.THUMBNAIL:
            from backend.connectors.flux import generate_image
            return generate_image
        else:
            raise ValueError(f"Unknown asset type: {asset_type}")

    # ----------------------------------------------------------
    # User decisions on assets
    # ----------------------------------------------------------
    async def approve_asset(self, asset_id: int):
        """
        User approved an asset.
        If it's an image, dispatch its animation (unless full_approve handles it).
        Check compile readiness.
        """
        ps = self._load()
        asset = ps.get_asset(asset_id)
        if not asset:
            return

        ps.update_asset(asset_id, state=AssetState.APPROVED)
        await worker.post(
            asset_state_msg(asset_id, asset["type"], AssetState.APPROVED)
        )

        # If image approved, dispatch animation
        if asset["type"] == AssetType.IMAGE:
            anim_prompt = f"Animate this image with subtle motion: {asset['prompt']}"
            anim_id = ps.next_asset_id()
            ps.add_asset(new_asset(anim_id, AssetType.ANIMATION, anim_prompt,
                                   linked_image_id=asset_id))
            ps.update_asset(asset_id, state=AssetState.ANIMATING)
            await worker.post(
                asset_state_msg(asset_id, AssetType.IMAGE, AssetState.ANIMATING)
            )
            asyncio.create_task(
                self._generate_asset(anim_id, AssetType.ANIMATION, anim_prompt)
            )

        await self._check_compile_ready()

    async def reject_asset(self, asset_id: int, note: str = ""):
        """User rejected an asset. Move to trash."""
        ps = self._load()
        asset = ps.get_asset(asset_id)
        if not asset:
            return

        ps.update_asset(asset_id, state=AssetState.REJECTED, notes=note)
        await worker.post(
            asset_state_msg(asset_id, asset["type"], AssetState.REJECTED)
        )

        trash = self._get_trash()
        assets_dir = _assets_dir(self.project_dir)
        files_to_trash = []

        if asset["filename"]:
            files_to_trash.append(
                str(Path(assets_dir) / asset["filename"])
            )
        prompt_file = str(
            Path(assets_dir) / _prompt_filename(asset_id, asset["type"])
        )
        files_to_trash.append(prompt_file)

        if files_to_trash:
            trash.move_to_trash(*files_to_trash)

    async def retry_asset(self, asset_id: int, new_prompt: Optional[str] = None):
        """
        User rejected and wants to retry with the same or edited prompt.
        Moves current files to trash, then dispatches a new generation.
        """
        ps = self._load()
        asset = ps.get_asset(asset_id)
        if not asset:
            return

        # Move current to trash first
        await self.reject_asset(asset_id)

        # Use new prompt if provided, otherwise reuse original
        prompt = new_prompt if new_prompt else asset["prompt"]
        ps.update_asset(asset_id, state=AssetState.PENDING,
                        prompt=prompt, filename=None, error_detail=None)

        asyncio.create_task(
            self._generate_asset(asset_id, asset["type"], prompt)
        )

    async def promote_to_thumbnail(self, asset_id: int):
        """Promote an approved image to the thumbnail slot."""
        ps = self._load()
        asset = ps.get_asset(asset_id)
        if not asset or asset["type"] not in (AssetType.IMAGE, AssetType.THUMBNAIL):
            return

        ps.update_asset(asset_id, state=AssetState.THUMBNAIL)
        await worker.post(
            asset_state_msg(asset_id, asset["type"], AssetState.THUMBNAIL)
        )

    async def freeze_asset(self, asset_id: int):
        """User chose to freeze an errored asset and deal with it later."""
        ps = self._load()
        asset = ps.get_asset(asset_id)
        if not asset:
            return
        ps.update_asset(asset_id, state=AssetState.FROZEN)
        await worker.post(
            asset_state_msg(asset_id, asset["type"], AssetState.FROZEN)
        )

    async def add_manual_asset(self, asset_type: str, prompt: str):
        """User manually adds a new asset from the dashboard."""
        ps = self._load()
        asset_id = ps.next_asset_id()
        ps.add_asset(new_asset(asset_id, asset_type, prompt))
        asyncio.create_task(
            self._generate_asset(asset_id, asset_type, prompt)
        )

    # ----------------------------------------------------------
    # Compile readiness
    # ----------------------------------------------------------
    async def _check_compile_ready(self):
        ps = self._load()
        minimums = get_compile_minimums(ps.get("format"))
        if ps.check_compile_ready(minimums):
            await worker.post(compile_ready_msg())
            ps.update_ui(AppPage.COMPILE)

    # ----------------------------------------------------------
    # Compile
    # ----------------------------------------------------------
    async def compile(self):
        """Trigger video compilation from approved assets."""
        from backend.compiler import compile_video
        ps = self._load()
        await worker.post(status_msg("Compiling video..."))
        ps.update_ui(AppPage.EXPORT)
        result = await with_retry(
            fn=lambda: compile_video(self.project_dir, ps.data),
            module="compiler"
        )
        if result["ok"]:
            ps.update("exported", True)
            await worker.post(status_msg("Compilation complete. Ready to export."))
        else:
            ps.add_error("compiler", result["error"]["detail"])
            await worker.post(
                project_error_msg("compiler", result["error"]["detail"])
            )
        return result

    # ----------------------------------------------------------
    # Publish (manual export package)
    # ----------------------------------------------------------
    async def mark_published(self, video_url: str):
        """
        Called after manual upload. Updates CSV and moves project to published/.
        """
        import shutil
        ps = self._load()

        # Update CSV
        csv_path = str(Path(CHANNELS_DIR) / self.channel / "topics.csv")
        if Path(csv_path).exists():
            store = TopicStore(csv_path)
            # Find matching topic by title
            for topic in store.get_all():
                if topic["name"] == ps.get("title"):
                    store.mark_published(int(topic["id"]), video_url)
                    break

        # Move project dir to published/
        published_dir = Path(CHANNELS_DIR) / self.channel / "published"
        published_dir.mkdir(exist_ok=True)
        shutil.move(self.project_dir,
                    str(published_dir / Path(self.project_dir).name))

        await worker.post(status_msg(f"Project published: {video_url}"))
