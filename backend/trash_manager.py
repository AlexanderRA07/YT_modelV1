# ==============================================================
# backend/trash_manager.py
# Manages the trash/ directory per project.
# Moves rejected assets to trash and auto-deletes after 2 days
# based on file system modification timestamp.
# Called on application startup.
# ==============================================================

import os
import shutil
import time
from pathlib import Path
from datetime import datetime

# Retention period in seconds (default 2 days, configurable via .env)
import os as _os
_RETENTION_DAYS = int(_os.getenv("TRASH_RETENTION_DAYS", "2"))
RETENTION_SECONDS = _RETENTION_DAYS * 86400


# ==============================================================
# TrashManager class
# ==============================================================
class TrashManager:
    """
    Manages the trash/ directory for a single project.
    Usage:
        tm = TrashManager("channels/my-channel/in-production/2024-01_my-video")
        tm.move_to_trash("assets/image3.jpg", "assets/prompt3.txt")
        tm.cleanup()   # called on startup to delete files older than 2 days
    """

    def __init__(self, project_dir: str):
        self.project_dir = Path(project_dir)
        self.trash_dir = self.project_dir / "trash"
        self.trash_dir.mkdir(parents=True, exist_ok=True)

    # ----------------------------------------------------------
    # Move to trash
    # ----------------------------------------------------------
    def move_to_trash(self, *file_paths: str):
        """
        Move one or more files into the trash/ directory.
        Accepts paths relative to project_dir or absolute paths.
        Paired files (e.g. prompt + asset) should be passed together.

        Example:
            tm.move_to_trash("assets/prompt3.txt", "assets/image3.jpg")
        """
        moved = []
        for file_path in file_paths:
            src = Path(file_path)
            if not src.is_absolute():
                src = self.project_dir / src

            if not src.exists():
                print(f"[TrashManager] Warning: file not found, skipping: {src}")
                continue

            dest = self.trash_dir / src.name

            # If a file with the same name already exists in trash, suffix it
            if dest.exists():
                stem = dest.stem
                suffix = dest.suffix
                timestamp = int(time.time())
                dest = self.trash_dir / f"{stem}_{timestamp}{suffix}"

            shutil.move(str(src), str(dest))
            moved.append(dest.name)

        if moved:
            print(f"[TrashManager] Moved to trash: {', '.join(moved)}")

        return moved

    # ----------------------------------------------------------
    # Cleanup (called on startup)
    # ----------------------------------------------------------
    def cleanup(self) -> list[str]:
        """
        Delete all files in trash/ whose modification time is older than
        RETENTION_SECONDS. Returns list of deleted filenames.
        Called automatically on application startup.
        """
        deleted = []
        now = time.time()

        for item in self.trash_dir.iterdir():
            if item.is_file():
                age = now - item.stat().st_mtime
                if age >= RETENTION_SECONDS:
                    item.unlink()
                    deleted.append(item.name)
                    print(f"[TrashManager] Auto-deleted: {item.name} "
                          f"(age: {age / 86400:.1f} days)")

        if not deleted:
            print(f"[TrashManager] Cleanup ran, nothing to delete in {self.trash_dir}")

        return deleted

    # ----------------------------------------------------------
    # Inspect trash
    # ----------------------------------------------------------
    def list_trash(self) -> list[dict]:
        """
        Return a list of dicts describing files currently in trash.
        Includes filename, size, age in hours, and scheduled deletion time.
        """
        now = time.time()
        result = []

        for item in self.trash_dir.iterdir():
            if item.is_file():
                age_seconds = now - item.stat().st_mtime
                seconds_remaining = max(0, RETENTION_SECONDS - age_seconds)
                result.append({
                    "filename":          item.name,
                    "size_kb":           round(item.stat().st_size / 1024, 1),
                    "age_hours":         round(age_seconds / 3600, 1),
                    "deletes_in_hours":  round(seconds_remaining / 3600, 1),
                    "modified":          datetime.fromtimestamp(
                                             item.stat().st_mtime
                                         ).isoformat()
                })

        return sorted(result, key=lambda x: x["age_hours"], reverse=True)

    def trash_count(self) -> int:
        """Return number of files currently in trash."""
        return sum(1 for item in self.trash_dir.iterdir() if item.is_file())

    def __repr__(self):
        return (f"TrashManager(project={self.project_dir.name}, "
                f"trash_count={self.trash_count()}, "
                f"retention={_RETENTION_DAYS}d)")


# ==============================================================
# Startup cleanup -- run across ALL projects on app start
# ==============================================================
def run_startup_cleanup(channels_dir: str) -> dict:
    """
    Walk all in-production project directories and run trash cleanup on each.
    Called once from main.py on application startup.

    Returns a summary dict: { project_name: [deleted_files] }
    """
    channels_path = Path(channels_dir)
    summary = {}

    if not channels_path.exists():
        print(f"[TrashManager] Channels directory not found: {channels_dir}")
        return summary

    for channel_dir in channels_path.iterdir():
        if not channel_dir.is_dir():
            continue
        in_production = channel_dir / "in-production"
        if not in_production.exists():
            continue
        for project_dir in in_production.iterdir():
            if not project_dir.is_dir():
                continue
            tm = TrashManager(str(project_dir))
            deleted = tm.cleanup()
            if deleted:
                summary[project_dir.name] = deleted

    print(f"[TrashManager] Startup cleanup complete. "
          f"Projects cleaned: {len(summary)}")
    return summary
