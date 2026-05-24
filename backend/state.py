# ==============================================================
# backend/state.py
# Project state management.
# Handles creation, loading, saving, and updating of
# project_state.json for each in-production project.
# Auto-saves on every change.
# ==============================================================

import json
import os
from datetime import datetime
from typing import Optional
from pathlib import Path


# --------------------------------------------------------------
# Asset state enum values (as constants for safety)
# --------------------------------------------------------------
class AssetState:
    WAITING    = "waiting"
    PENDING    = "pending"
    REVIEW     = "review"
    APPROVED   = "approved"
    REJECTED   = "rejected"
    FROZEN     = "frozen"
    ERROR      = "error"
    ANIMATING  = "animating"
    THUMBNAIL  = "thumbnail"
    DONE       = "done"


# --------------------------------------------------------------
# Asset type enum values
# --------------------------------------------------------------
class AssetType:
    IMAGE      = "image"
    ANIMATION  = "animation"
    VOICE      = "voice"
    MUSIC      = "music"
    THUMBNAIL  = "thumbnail"


# --------------------------------------------------------------
# Page/position identifiers for exact restore
# --------------------------------------------------------------
class AppPage:
    HOME            = "home"
    NEW_PROJECT     = "new_project"
    SCRIPT_REVIEW   = "script_review"
    DASHBOARD       = "dashboard"
    COMPILE         = "compile"
    EXPORT          = "export"
    FINISHED        = "finished"


# --------------------------------------------------------------
# Default project state structure
# --------------------------------------------------------------
def default_project_state(project_id: str, title: str, niche: str,
                           description: str, format: str,
                           channel: str) -> dict:
    return {
        # --- Identity ---
        "project_id":   project_id,
        "title":        title,
        "niche":        niche,
        "description":  description,
        "format":       format,        # "1min" | "2min" | "10min" | "15min"
        "channel":      channel,
        "created_at":   datetime.now().isoformat(),
        "updated_at":   datetime.now().isoformat(),

        # --- UI restore ---
        "current_page": AppPage.SCRIPT_REVIEW,
        "queue_position": 0,           # index in review queue

        # --- Pipeline flags ---
        "full_approve": False,         # True if user chose Full Approve
        "script_approved": False,
        "compile_ready": False,
        "exported": False,

        # --- Script ---
        "script": {
            "draft": "",               # AI-generated draft
            "final": "",               # user-edited final
            "tags": [],
            "shot_list": []            # list of shot dicts from script stage
        },

        # --- Assets ---
        # Each asset is a dict (see new_asset() below)
        "assets": [],

        # --- Errors ---
        # Frozen module errors waiting for user action
        "errors": [],

        # --- Sources ---
        # Populated by scraper and script stage
        "sources": []
    }


# --------------------------------------------------------------
# Asset record structure
# --------------------------------------------------------------
def new_asset(asset_id: int, asset_type: str,
              prompt: str, linked_image_id: Optional[int] = None) -> dict:
    """
    Create a new asset record.
    asset_id        -- numeric ID, shared with prompt file (e.g. 3 -> prompt3.txt / image3.jpg)
    asset_type      -- AssetType constant
    prompt          -- the text prompt sent to the AI engine
    linked_image_id -- for animations only, the image asset_id this is paired with
    """
    return {
        "asset_id":        asset_id,
        "type":            asset_type,
        "state":           AssetState.PENDING,
        "prompt":          prompt,
        "linked_image_id": linked_image_id,   # animations only
        "filename":        None,              # set when asset is returned
        "retry_count":     0,
        "error_detail":    None,
        "created_at":      datetime.now().isoformat(),
        "updated_at":      datetime.now().isoformat(),
        "notes":           ""                 # optional rejection notes
    }


# --------------------------------------------------------------
# Error record structure
# --------------------------------------------------------------
def new_error(module: str, detail: str, asset_id: Optional[int] = None) -> dict:
    return {
        "module":     module,       # e.g. "kling", "elevenlabs", "pipeline"
        "detail":     detail,       # full error message
        "asset_id":   asset_id,     # linked asset if applicable
        "resolved":   False,
        "created_at": datetime.now().isoformat()
    }


# ==============================================================
# ProjectState class
# ==============================================================
class ProjectState:
    """
    Wraps a project's state dict and auto-saves to disk on every mutation.
    Usage:
        ps = ProjectState.load(project_dir)
        ps.update("script_approved", True)
        ps.add_asset(new_asset(1, AssetType.IMAGE, "a watercolor forest"))
    """

    def __init__(self, project_dir: str, state: dict):
        self.project_dir = Path(project_dir)
        self._state = state
        self._path = self.project_dir / "project_state.json"

    # ----------------------------------------------------------
    # Load or create
    # ----------------------------------------------------------
    @classmethod
    def load(cls, project_dir: str) -> "ProjectState":
        """Load existing project_state.json from disk."""
        path = Path(project_dir) / "project_state.json"
        if not path.exists():
            raise FileNotFoundError(f"No project_state.json found at {path}")
        with open(path, "r", encoding="utf-8") as f:
            state = json.load(f)
        return cls(project_dir, state)

    @classmethod
    def create(cls, project_dir: str, project_id: str, title: str,
               niche: str, description: str, format: str,
               channel: str) -> "ProjectState":
        """Create a new project state and immediately save it."""
        os.makedirs(project_dir, exist_ok=True)
        state = default_project_state(
            project_id, title, niche, description, format, channel
        )
        ps = cls(project_dir, state)
        ps._save()
        return ps

    # ----------------------------------------------------------
    # Save
    # ----------------------------------------------------------
    def _save(self):
        """Write state to disk. Called automatically after every mutation."""
        self._state["updated_at"] = datetime.now().isoformat()
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._state, f, indent=2, ensure_ascii=False)

    # ----------------------------------------------------------
    # Read
    # ----------------------------------------------------------
    @property
    def data(self) -> dict:
        """Return a copy of the full state dict (read-only snapshot)."""
        return dict(self._state)

    def get(self, key: str):
        return self._state.get(key)

    # ----------------------------------------------------------
    # Update top-level fields
    # ----------------------------------------------------------
    def update(self, key: str, value):
        """Set a top-level field and auto-save."""
        self._state[key] = value
        self._save()

    def update_ui(self, page: str, queue_position: int = 0):
        """Update the UI restore position and auto-save."""
        self._state["current_page"] = page
        self._state["queue_position"] = queue_position
        self._save()

    def update_script(self, draft: str = None, final: str = None, tags: list = None, shot_list: list = None, description: str = None, credits: str = None):
        """Update any combination of script fields and auto-save."""
        if draft       is not None: self._state["script"]["draft"]       = draft
        if final       is not None: self._state["script"]["final"]       = final
        if tags        is not None: self._state["script"]["tags"]        = tags
        if shot_list   is not None: self._state["script"]["shot_list"]   = shot_list
        if description is not None: self._state["script"]["description"] = description
        if credits     is not None: self._state["script"]["credits"]     = credits
        self._save()

    # ----------------------------------------------------------
    # Asset operations
    # ----------------------------------------------------------
    def add_asset(self, asset: dict):
        """Append a new asset record and auto-save."""
        self._state["assets"].append(asset)
        self._save()

    def update_asset(self, asset_id: int, **kwargs):
        """
        Update fields on an asset by its asset_id and auto-save.
        Example: ps.update_asset(3, state=AssetState.APPROVED, filename="image3.jpg")
        """
        for asset in self._state["assets"]:
            if asset["asset_id"] == asset_id:
                for key, value in kwargs.items():
                    asset[key] = value
                asset["updated_at"] = datetime.now().isoformat()
                self._save()
                return
        raise ValueError(f"Asset with id {asset_id} not found.")

    def get_asset(self, asset_id: int) -> Optional[dict]:
        """Return a single asset dict by id, or None."""
        for asset in self._state["assets"]:
            if asset["asset_id"] == asset_id:
                return asset
        return None

    def get_assets_by_state(self, state: str) -> list:
        """Return all assets currently in a given state."""
        return [a for a in self._state["assets"] if a["state"] == state]

    def get_assets_by_type(self, asset_type: str) -> list:
        """Return all assets of a given type."""
        return [a for a in self._state["assets"] if a["type"] == asset_type]

    def count_approved(self, asset_type: str) -> int:
        """Count approved assets of a given type."""
        return sum(
            1 for a in self._state["assets"]
            if a["type"] == asset_type
            and a["state"] in (AssetState.APPROVED, AssetState.DONE, AssetState.THUMBNAIL)
        )

    def next_asset_id(self) -> int:
        """Return the next available asset_id (increments from highest existing)."""
        if not self._state["assets"]:
            return 1
        return max(a["asset_id"] for a in self._state["assets"]) + 1

    # ----------------------------------------------------------
    # Error operations
    # ----------------------------------------------------------
    def add_error(self, module: str, detail: str,
                  asset_id: Optional[int] = None):
        """Log an error and auto-save."""
        self._state["errors"].append(new_error(module, detail, asset_id))
        self._save()

    def resolve_error(self, module: str, asset_id: Optional[int] = None):
        """Mark a matching error as resolved and auto-save."""
        for error in self._state["errors"]:
            if error["module"] == module and error["asset_id"] == asset_id:
                error["resolved"] = True
        self._save()

    # ----------------------------------------------------------
    # Source tracking
    # ----------------------------------------------------------
    def add_source(self, url: str, title: str = "", note: str = ""):
        """Log a research source and auto-save."""
        self._state["sources"].append({
            "url":        url,
            "title":      title,
            "note":       note,
            "added_at":   datetime.now().isoformat()
        })
        self._save()

    # ----------------------------------------------------------
    # Compile readiness check
    # ----------------------------------------------------------
    def check_compile_ready(self, minimums: dict) -> bool:
        """
        Check if minimum approved asset counts are met.
        minimums: { "image": 2, "animation": 2, "voice": 1, "music": 1, "thumbnail": 1 }
        Sets and saves compile_ready flag. Returns True/False.
        """
        ready = all(
            self.count_approved(asset_type) >= count
            for asset_type, count in minimums.items()
        )
        self._state["compile_ready"] = ready
        self._save()
        return ready

    def __repr__(self):
        return (f"ProjectState(id={self._state['project_id']}, "
                f"title={self._state['title']!r}, "
                f"page={self._state['current_page']})")
