# ==============================================================
# backend/csv_manager.py
# Handles all reading and writing of topics.csv per channel.
# ==============================================================

import csv
import os
import random
from datetime import datetime
from pathlib import Path


# --------------------------------------------------------------
# Topic status enum
# --------------------------------------------------------------
class TopicStatus:
    IDEA          = "idea"
    IN_PRODUCTION = "in_production"
    PUBLISHED     = "published"
    SHELVED       = "shelved"


# --------------------------------------------------------------
# CSV schema (column order matters for file consistency)
# --------------------------------------------------------------
FIELDNAMES = [
    "id",
    "name",
    "niche",
    "description",
    "format",           # pre-set target length: 1min | 2min | 10min | 15min (optional)
    "references",       # semicolon-separated source URLs for script research
    "concepts",         # free-text creative directions / angles to incorporate
    "status",
    "video_url",
    "date_added",
    "date_published"
]


# ==============================================================
# TopicStore class
# ==============================================================
class TopicStore:
    """
    Manages a channel's topics.csv file.
    Usage:
        store = TopicStore("channels/my-channel/topics.csv")
        store.add_topic("Black Holes", "science", "How black holes form and what lies inside.")
        available = store.get_available()
        sample = store.random_sample(10)
    """

    def __init__(self, csv_path: str):
        self.path = Path(csv_path)
        self._ensure_file()

    # ----------------------------------------------------------
    # Internal helpers
    # ----------------------------------------------------------
    def _ensure_file(self):
        """Create topics.csv with headers if it does not exist."""
        if not self.path.exists():
            os.makedirs(self.path.parent, exist_ok=True)
            with open(self.path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
                writer.writeheader()

    def _read_all(self) -> list[dict]:
        """Read all rows from CSV and return as list of dicts."""
        with open(self.path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return list(reader)

    def _write_all(self, rows: list[dict]):
        """Overwrite the CSV with the given rows."""
        with open(self.path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerows(rows)

    def _next_id(self, rows: list[dict]) -> int:
        """Return next available numeric ID."""
        if not rows:
            return 1
        return max(int(r["id"]) for r in rows) + 1

    # ----------------------------------------------------------
    # Read operations
    # ----------------------------------------------------------
    def get_all(self) -> list[dict]:
        """Return all topics."""
        return self._read_all()

    def get_by_id(self, topic_id: int) -> dict | None:
        """Return a single topic by id, or None."""
        for row in self._read_all():
            if int(row["id"]) == topic_id:
                return row
        return None

    def get_available(self) -> list[dict]:
        """
        Return all topics with status 'idea' (available to start production).
        These are the topics eligible for 'Draw from CSV' in the UI.
        """
        return [r for r in self._read_all() if r["status"] == TopicStatus.IDEA]

    def get_in_production(self) -> list[dict]:
        """Return all topics currently in production."""
        return [r for r in self._read_all() if r["status"] == TopicStatus.IN_PRODUCTION]

    def get_published(self) -> list[dict]:
        """Return all published topics."""
        return [r for r in self._read_all() if r["status"] == TopicStatus.PUBLISHED]

    def count_available(self) -> int:
        """Return count of available (idea) topics."""
        return len(self.get_available())

    def random_sample(self, n: int = 10) -> list[dict]:
        """
        Return up to n randomly selected available topics.
        If fewer than n are available, returns all available.
        """
        available = self.get_available()
        return random.sample(available, min(n, len(available)))

    # ----------------------------------------------------------
    # Write operations
    # ----------------------------------------------------------
    def add_topic(self, name: str, niche: str, description: str,
                  format: str = "", references: str = "",
                  concepts: str = "") -> dict:
        """
        Add a new topic with status 'idea' and today's date.
        Returns the new topic dict.
        """
        rows = self._read_all()
        new_row = {
            "id":             self._next_id(rows),
            "name":           name,
            "niche":          niche,
            "description":    description,
            "format":         format,
            "references":     references,
            "concepts":       concepts,
            "status":         TopicStatus.IDEA,
            "video_url":      "",
            "date_added":     datetime.now().strftime("%Y-%m-%d"),
            "date_published": ""
        }
        rows.append(new_row)
        self._write_all(rows)
        return new_row

    def update_topic(self, topic_id: int, **kwargs) -> dict | None:
        """
        Update editable fields on a topic by id.
        Allowed fields: name, niche, description, format, references, concepts.
        Returns the updated row or None if not found.
        """
        editable = {"name", "niche", "description", "format", "references", "concepts"}
        rows = self._read_all()
        for row in rows:
            if int(row["id"]) == topic_id:
                for key, val in kwargs.items():
                    if key in editable:
                        row[key] = val
                self._write_all(rows)
                return row
        return None

    def update_status(self, topic_id: int, status: str,
                      video_url: str = None):
        """
        Update the status of a topic by id.
        Optionally set video_url and date_published when marking as published.
        """
        rows = self._read_all()
        for row in rows:
            if int(row["id"]) == topic_id:
                row["status"] = status
                if video_url:
                    row["video_url"] = video_url
                if status == TopicStatus.PUBLISHED:
                    row["date_published"] = datetime.now().strftime("%Y-%m-%d")
                break
        self._write_all(rows)

    def mark_in_production(self, topic_id: int):
        """Convenience: mark a topic as in_production."""
        self.update_status(topic_id, TopicStatus.IN_PRODUCTION)

    def mark_published(self, topic_id: int, video_url: str):
        """Convenience: mark a topic as published and record the video URL."""
        self.update_status(topic_id, TopicStatus.PUBLISHED, video_url=video_url)

    def mark_shelved(self, topic_id: int):
        """Convenience: mark a topic as shelved."""
        self.update_status(topic_id, TopicStatus.SHELVED)

    def delete_topic(self, topic_id: int):
        """
        Remove a topic from the CSV entirely.
        Use sparingly -- prefer 'shelved' to keep history.
        """
        rows = self._read_all()
        rows = [r for r in rows if int(r["id"]) != topic_id]
        self._write_all(rows)

    def __repr__(self):
        return f"TopicStore(path={self.path}, total={len(self.get_all())})"
