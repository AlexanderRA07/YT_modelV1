# ==============================================================
# tests/frontend/test_api.py
# Integration tests for the FastAPI REST endpoints.
# Uses FastAPI's TestClient — no real browser or network calls.
# The CHANNELS_DIR is redirected to a temp directory so the
# real channels/ folder is never touched.
# ==============================================================

import os
import shutil
import tempfile
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

# Point CHANNELS_DIR at a temp location before the app imports it
_TMP_CHANNELS = tempfile.mkdtemp()
os.environ["CHANNELS_DIR"] = _TMP_CHANNELS

from backend.api import app
from backend.csv_manager import TopicStore

CHANNEL = "test-channel"
CSV_PATH = Path(_TMP_CHANNELS) / CHANNEL / "topics.csv"


# --------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------

@pytest.fixture(autouse=True)
def fresh_channel():
    """Create a clean channel directory with two seed topics before each test."""
    shutil.rmtree(str(CSV_PATH.parent), ignore_errors=True)
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    store = TopicStore(str(CSV_PATH))
    store.add_topic("Black Holes", "science", "How they form")
    store.add_topic("Darth Vader", "star wars", "His injuries on Mustafar")
    yield
    shutil.rmtree(str(CSV_PATH.parent), ignore_errors=True)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


# --------------------------------------------------------------
# Channel listing
# --------------------------------------------------------------

class TestChannelListing:
    def test_lists_existing_channel(self, client):
        resp = client.get("/api/channels")
        assert resp.status_code == 200
        assert CHANNEL in resp.json()

    def test_missing_channel_topics_returns_404(self, client):
        resp = client.get("/api/channels/nonexistent/topics/available")
        assert resp.status_code == 404


# --------------------------------------------------------------
# Topic read routes
# --------------------------------------------------------------

class TestTopicRead:
    def test_available_count(self, client):
        resp = client.get(f"/api/channels/{CHANNEL}/topics/available")
        assert resp.status_code == 200
        assert resp.json()["count"] == 2

    def test_sample_returns_topics(self, client):
        resp = client.get(f"/api/channels/{CHANNEL}/topics/sample?n=10")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_all_topics_returns_all(self, client):
        resp = client.get(f"/api/channels/{CHANNEL}/topics/all")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_get_niches_returns_both_niches(self, client):
        resp = client.get(f"/api/channels/{CHANNEL}/niches")
        assert resp.status_code == 200
        niches = resp.json()["niches"]
        assert "science" in niches
        assert "star wars" in niches


# --------------------------------------------------------------
# Add topic
# --------------------------------------------------------------

class TestAddTopic:
    def test_add_minimal_topic(self, client):
        payload = {"name": "Flumph", "niche": "dnd", "description": "A weird creature"}
        resp = client.post(f"/api/channels/{CHANNEL}/topics/add", json=payload)
        assert resp.status_code == 200
        topic = resp.json()
        assert topic["name"] == "Flumph"
        assert topic["status"] == "idea"

    def test_add_topic_with_new_schema_fields(self, client):
        payload = {
            "name": "Tarasque",
            "niche": "dnd",
            "description": "Boss monster lore",
            "format": "10min",
            "references": "https://dndbeyond.com;https://forgottenrealms.fandom.com",
            "concepts": "open with a civilian POV narrative"
        }
        resp = client.post(f"/api/channels/{CHANNEL}/topics/add", json=payload)
        assert resp.status_code == 200
        topic = resp.json()
        assert topic["format"] == "10min"
        assert topic["references"] == "https://dndbeyond.com;https://forgottenrealms.fandom.com"
        assert topic["concepts"] == "open with a civilian POV narrative"

    def test_add_topic_increases_available_count(self, client):
        client.post(
            f"/api/channels/{CHANNEL}/topics/add",
            json={"name": "New Topic", "niche": "science"}
        )
        resp = client.get(f"/api/channels/{CHANNEL}/topics/available")
        assert resp.json()["count"] == 3


# --------------------------------------------------------------
# Update topic (PATCH)
# --------------------------------------------------------------

class TestUpdateTopic:
    def test_update_references_and_concepts(self, client):
        resp = client.patch(
            f"/api/channels/{CHANNEL}/topics/1",
            json={"references": "https://nasa.gov", "concepts": "be scientific and clear"}
        )
        assert resp.status_code == 200
        topic = resp.json()
        assert topic["references"] == "https://nasa.gov"
        assert topic["concepts"] == "be scientific and clear"

    def test_update_format(self, client):
        resp = client.patch(
            f"/api/channels/{CHANNEL}/topics/1",
            json={"format": "15min"}
        )
        assert resp.status_code == 200
        assert resp.json()["format"] == "15min"

    def test_update_nonexistent_topic_returns_404(self, client):
        resp = client.patch(
            f"/api/channels/{CHANNEL}/topics/999",
            json={"name": "Ghost"}
        )
        assert resp.status_code == 404

    def test_partial_update_leaves_other_fields_intact(self, client):
        # Seed name is "Black Holes"; update only concepts
        client.patch(
            f"/api/channels/{CHANNEL}/topics/1",
            json={"concepts": "mention event horizon"}
        )
        all_topics = client.get(f"/api/channels/{CHANNEL}/topics/all").json()
        topic = next(t for t in all_topics if t["id"] == "1")
        assert topic["name"] == "Black Holes"
        assert topic["concepts"] == "mention event horizon"


# --------------------------------------------------------------
# Health check
# --------------------------------------------------------------

class TestHealth:
    def test_health_endpoint_exists(self, client):
        # The connectors may not be reachable in CI, but the route should respond
        resp = client.get("/api/health")
        assert resp.status_code == 200
        body = resp.json()
        for key in ["flux", "kling", "elevenlabs", "suno"]:
            assert key in body
