# ==============================================================
# tests/backend/test_csv_manager.py
# Unit tests for TopicStore (csv_manager.py).
# Uses a temporary file so the real topics.csv is never touched.
# ==============================================================

import csv
import pytest
from pathlib import Path

from backend.csv_manager import TopicStore, TopicStatus, FIELDNAMES


@pytest.fixture
def csv_path(tmp_path):
    return str(tmp_path / "topics.csv")


# --------------------------------------------------------------
# File creation
# --------------------------------------------------------------

class TestFileCreation:
    def test_creates_file_with_correct_headers(self, csv_path):
        TopicStore(csv_path)
        assert Path(csv_path).exists()
        with open(csv_path) as f:
            reader = csv.DictReader(f)
            assert reader.fieldnames == FIELDNAMES

    def test_does_not_overwrite_existing_file(self, csv_path):
        store = TopicStore(csv_path)
        store.add_topic("Test", "science", "A test topic")
        TopicStore(csv_path)  # re-open
        assert len(TopicStore(csv_path).get_all()) == 1


# --------------------------------------------------------------
# add_topic
# --------------------------------------------------------------

class TestAddTopic:
    def test_basic_add(self, csv_path):
        store = TopicStore(csv_path)
        topic = store.add_topic("Black Holes", "science", "How they form")
        assert topic["id"] == "1"
        assert topic["name"] == "Black Holes"
        assert topic["niche"] == "science"
        assert topic["status"] == TopicStatus.IDEA

    def test_new_schema_fields_stored(self, csv_path):
        store = TopicStore(csv_path)
        topic = store.add_topic(
            "Tarasque", "dnd", "Boss lore",
            format="10min",
            references="https://dndbeyond.com;https://wiki.example.com",
            concepts="open with a civilian POV narrative"
        )
        assert topic["format"] == "10min"
        assert topic["references"] == "https://dndbeyond.com;https://wiki.example.com"
        assert topic["concepts"] == "open with a civilian POV narrative"

    def test_ids_auto_increment(self, csv_path):
        store = TopicStore(csv_path)
        t1 = store.add_topic("A", "n", "d")
        t2 = store.add_topic("B", "n", "d")
        assert int(t2["id"]) == int(t1["id"]) + 1

    def test_date_added_is_set(self, csv_path):
        store = TopicStore(csv_path)
        topic = store.add_topic("X", "n", "d")
        assert topic["date_added"] != ""

    def test_default_new_fields_are_empty(self, csv_path):
        store = TopicStore(csv_path)
        topic = store.add_topic("Y", "n", "d")
        assert topic["format"] == ""
        assert topic["references"] == ""
        assert topic["concepts"] == ""


# --------------------------------------------------------------
# Getters
# --------------------------------------------------------------

class TestGetters:
    def test_get_all(self, csv_path):
        store = TopicStore(csv_path)
        store.add_topic("A", "n", "d")
        store.add_topic("B", "n", "d")
        assert len(store.get_all()) == 2

    def test_get_by_id_found(self, csv_path):
        store = TopicStore(csv_path)
        store.add_topic("A", "n", "d")
        store.add_topic("B", "n", "d")
        result = store.get_by_id(2)
        assert result["name"] == "B"

    def test_get_by_id_missing(self, csv_path):
        store = TopicStore(csv_path)
        assert store.get_by_id(99) is None

    def test_get_available_excludes_non_idea(self, csv_path):
        store = TopicStore(csv_path)
        store.add_topic("A", "n", "d")
        store.add_topic("B", "n", "d")
        store.mark_in_production(1)
        available = store.get_available()
        assert len(available) == 1
        assert available[0]["name"] == "B"

    def test_random_sample_respects_n(self, csv_path):
        store = TopicStore(csv_path)
        for i in range(5):
            store.add_topic(f"Topic {i}", "n", "d")
        sample = store.random_sample(3)
        assert len(sample) == 3

    def test_random_sample_returns_all_if_fewer_than_n(self, csv_path):
        store = TopicStore(csv_path)
        store.add_topic("A", "n", "d")
        sample = store.random_sample(10)
        assert len(sample) == 1

    def test_count_available(self, csv_path):
        store = TopicStore(csv_path)
        store.add_topic("A", "n", "d")
        store.add_topic("B", "n", "d")
        store.mark_in_production(1)
        assert store.count_available() == 1


# --------------------------------------------------------------
# Status transitions
# --------------------------------------------------------------

class TestStatusTransitions:
    def test_mark_in_production(self, csv_path):
        store = TopicStore(csv_path)
        store.add_topic("A", "n", "d")
        store.mark_in_production(1)
        assert store.get_by_id(1)["status"] == TopicStatus.IN_PRODUCTION

    def test_mark_published_sets_url_and_date(self, csv_path):
        store = TopicStore(csv_path)
        store.add_topic("A", "n", "d")
        store.mark_published(1, "https://youtube.com/watch?v=abc")
        row = store.get_by_id(1)
        assert row["status"] == TopicStatus.PUBLISHED
        assert row["video_url"] == "https://youtube.com/watch?v=abc"
        assert row["date_published"] != ""

    def test_mark_shelved(self, csv_path):
        store = TopicStore(csv_path)
        store.add_topic("A", "n", "d")
        store.mark_shelved(1)
        assert store.get_by_id(1)["status"] == TopicStatus.SHELVED


# --------------------------------------------------------------
# update_topic
# --------------------------------------------------------------

class TestUpdateTopic:
    def test_update_name(self, csv_path):
        store = TopicStore(csv_path)
        store.add_topic("Old Name", "n", "d")
        store.update_topic(1, name="New Name")
        assert store.get_by_id(1)["name"] == "New Name"

    def test_update_references_and_concepts(self, csv_path):
        store = TopicStore(csv_path)
        store.add_topic("A", "n", "d")
        store.update_topic(1, references="https://example.com", concepts="be dramatic")
        row = store.get_by_id(1)
        assert row["references"] == "https://example.com"
        assert row["concepts"] == "be dramatic"

    def test_update_nonexistent_returns_none(self, csv_path):
        store = TopicStore(csv_path)
        assert store.update_topic(99, name="Ghost") is None

    def test_update_does_not_change_status(self, csv_path):
        # status is not in the editable set; changes should be silently ignored
        store = TopicStore(csv_path)
        store.add_topic("A", "n", "d")
        store.update_topic(1, status="published")
        assert store.get_by_id(1)["status"] == TopicStatus.IDEA


# --------------------------------------------------------------
# delete_topic
# --------------------------------------------------------------

class TestDeleteTopic:
    def test_delete_removes_row(self, csv_path):
        store = TopicStore(csv_path)
        store.add_topic("A", "n", "d")
        store.add_topic("B", "n", "d")
        store.delete_topic(1)
        assert len(store.get_all()) == 1
        assert store.get_by_id(1) is None

    def test_delete_nonexistent_is_noop(self, csv_path):
        store = TopicStore(csv_path)
        store.add_topic("A", "n", "d")
        store.delete_topic(99)
        assert len(store.get_all()) == 1
