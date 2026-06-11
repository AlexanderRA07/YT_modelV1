# ==============================================================
# tests/backend/test_state.py
# Unit tests for ProjectState (state.py).
# All tests use a temporary directory; nothing is written to disk
# in the project tree.
# ==============================================================

import pytest
from pathlib import Path

from backend.state import (
    ProjectState, AssetState, AssetType, AppPage,
    default_project_state, new_asset
)


@pytest.fixture
def project_dir(tmp_path):
    d = tmp_path / "test_project"
    d.mkdir()
    return str(d)


# --------------------------------------------------------------
# default_project_state
# --------------------------------------------------------------

class TestDefaultProjectState:
    def test_all_required_keys_present(self):
        state = default_project_state("pid", "Title", "niche", "desc", "10min", "ch")
        required = [
            "project_id", "title", "niche", "description", "format",
            "channel", "references", "concepts",
            "current_page", "script", "assets", "errors", "sources",
            "script_approved", "compile_ready", "exported",
        ]
        for key in required:
            assert key in state, f"Missing key: {key}"

    def test_references_and_concepts_default_empty(self):
        state = default_project_state("pid", "T", "n", "d", "2min", "ch")
        assert state["references"] == ""
        assert state["concepts"] == ""

    def test_references_and_concepts_passed_through(self):
        state = default_project_state(
            "pid", "T", "n", "d", "2min", "ch",
            references="http://a.com", concepts="be dramatic"
        )
        assert state["references"] == "http://a.com"
        assert state["concepts"] == "be dramatic"

    def test_script_sub_keys(self):
        state = default_project_state("pid", "T", "n", "d", "2min", "ch")
        for key in ["draft", "final", "tags", "shot_list"]:
            assert key in state["script"]


# --------------------------------------------------------------
# ProjectState.create and .load
# --------------------------------------------------------------

class TestCreateLoad:
    def test_create_writes_json(self, project_dir):
        ProjectState.create(project_dir, "pid", "Title", "niche", "desc", "10min", "ch")
        assert (Path(project_dir) / "project_state.json").exists()

    def test_load_round_trips_basic_fields(self, project_dir):
        ProjectState.create(project_dir, "pid", "Title", "niche", "desc", "10min", "ch")
        ps = ProjectState.load(project_dir)
        assert ps.get("title") == "Title"
        assert ps.get("niche") == "niche"
        assert ps.get("format") == "10min"

    def test_load_round_trips_new_fields(self, project_dir):
        ProjectState.create(
            project_dir, "pid", "T", "n", "d", "2min", "ch",
            references="http://x.com", concepts="open with drama"
        )
        ps = ProjectState.load(project_dir)
        assert ps.get("references") == "http://x.com"
        assert ps.get("concepts") == "open with drama"

    def test_load_missing_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            ProjectState.load(str(tmp_path / "nonexistent"))


# --------------------------------------------------------------
# update / update_ui / update_script
# --------------------------------------------------------------

class TestUpdates:
    def test_update_top_level(self, project_dir):
        ps = ProjectState.create(project_dir, "pid", "T", "n", "d", "2min", "ch")
        ps.update("full_approve", True)
        ps2 = ProjectState.load(project_dir)
        assert ps2.get("full_approve") is True

    def test_update_ui_page_and_position(self, project_dir):
        ps = ProjectState.create(project_dir, "pid", "T", "n", "d", "2min", "ch")
        ps.update_ui(AppPage.DASHBOARD, queue_position=3)
        ps2 = ProjectState.load(project_dir)
        assert ps2.get("current_page") == AppPage.DASHBOARD
        assert ps2.get("queue_position") == 3

    def test_update_script_fields(self, project_dir):
        ps = ProjectState.create(project_dir, "pid", "T", "n", "d", "2min", "ch")
        ps.update_script(draft="Draft text", tags=["sci-fi", "lore"])
        ps2 = ProjectState.load(project_dir)
        assert ps2.get("script")["draft"] == "Draft text"
        assert ps2.get("script")["tags"] == ["sci-fi", "lore"]

    def test_update_script_partial_leaves_others_intact(self, project_dir):
        ps = ProjectState.create(project_dir, "pid", "T", "n", "d", "2min", "ch")
        ps.update_script(draft="Initial draft", tags=["tag1"])
        ps.update_script(tags=["tag2"])
        # draft should be unchanged
        assert ps.get("script")["draft"] == "Initial draft"
        assert ps.get("script")["tags"] == ["tag2"]


# --------------------------------------------------------------
# Asset operations
# --------------------------------------------------------------

class TestAssets:
    def test_add_and_retrieve_asset(self, project_dir):
        ps = ProjectState.create(project_dir, "pid", "T", "n", "d", "2min", "ch")
        ps.add_asset(new_asset(1, AssetType.IMAGE, "a forest"))
        result = ps.get_asset(1)
        assert result is not None
        assert result["type"] == AssetType.IMAGE
        assert result["prompt"] == "a forest"

    def test_update_asset_state_and_filename(self, project_dir):
        ps = ProjectState.create(project_dir, "pid", "T", "n", "d", "2min", "ch")
        ps.add_asset(new_asset(1, AssetType.IMAGE, "a forest"))
        ps.update_asset(1, state=AssetState.APPROVED, filename="image1.jpg")
        asset = ps.get_asset(1)
        assert asset["state"] == AssetState.APPROVED
        assert asset["filename"] == "image1.jpg"

    def test_update_missing_asset_raises(self, project_dir):
        ps = ProjectState.create(project_dir, "pid", "T", "n", "d", "2min", "ch")
        with pytest.raises(ValueError):
            ps.update_asset(99, state=AssetState.APPROVED)

    def test_next_asset_id_starts_at_one(self, project_dir):
        ps = ProjectState.create(project_dir, "pid", "T", "n", "d", "2min", "ch")
        assert ps.next_asset_id() == 1

    def test_next_asset_id_increments(self, project_dir):
        ps = ProjectState.create(project_dir, "pid", "T", "n", "d", "2min", "ch")
        ps.add_asset(new_asset(1, AssetType.IMAGE, "x"))
        assert ps.next_asset_id() == 2

    def test_get_assets_by_state(self, project_dir):
        ps = ProjectState.create(project_dir, "pid", "T", "n", "d", "2min", "ch")
        ps.add_asset(new_asset(1, AssetType.IMAGE, "x"))
        ps.add_asset(new_asset(2, AssetType.VOICE, "y"))
        ps.update_asset(1, state=AssetState.APPROVED)
        approved = ps.get_assets_by_state(AssetState.APPROVED)
        assert len(approved) == 1
        assert approved[0]["asset_id"] == 1

    def test_get_assets_by_type(self, project_dir):
        ps = ProjectState.create(project_dir, "pid", "T", "n", "d", "2min", "ch")
        ps.add_asset(new_asset(1, AssetType.IMAGE, "x"))
        ps.add_asset(new_asset(2, AssetType.IMAGE, "y"))
        ps.add_asset(new_asset(3, AssetType.VOICE, "z"))
        images = ps.get_assets_by_type(AssetType.IMAGE)
        assert len(images) == 2

    def test_count_approved_by_type(self, project_dir):
        ps = ProjectState.create(project_dir, "pid", "T", "n", "d", "2min", "ch")
        ps.add_asset(new_asset(1, AssetType.IMAGE, "x"))
        ps.add_asset(new_asset(2, AssetType.IMAGE, "y"))
        ps.update_asset(1, state=AssetState.APPROVED)
        assert ps.count_approved(AssetType.IMAGE) == 1
        assert ps.count_approved(AssetType.VOICE) == 0


# --------------------------------------------------------------
# Compile readiness
# --------------------------------------------------------------

class TestCompileReadiness:
    def test_not_ready_with_no_assets(self, project_dir):
        ps = ProjectState.create(project_dir, "pid", "T", "n", "d", "2min", "ch")
        mins = {"image": 1, "animation": 1, "voice": 1, "music": 1, "thumbnail": 1}
        assert ps.check_compile_ready(mins) is False

    def test_ready_when_all_minimums_met(self, project_dir):
        ps = ProjectState.create(project_dir, "pid", "T", "n", "d", "2min", "ch")
        for i, atype in enumerate(
            [AssetType.IMAGE, AssetType.ANIMATION, AssetType.VOICE,
             AssetType.MUSIC, AssetType.THUMBNAIL], start=1
        ):
            ps.add_asset(new_asset(i, atype, "x"))
            ps.update_asset(i, state=AssetState.APPROVED)
        mins = {"image": 1, "animation": 1, "voice": 1, "music": 1, "thumbnail": 1}
        assert ps.check_compile_ready(mins) is True

    def test_not_ready_when_one_type_short(self, project_dir):
        ps = ProjectState.create(project_dir, "pid", "T", "n", "d", "2min", "ch")
        # Approve everything except music
        for i, atype in enumerate(
            [AssetType.IMAGE, AssetType.ANIMATION, AssetType.VOICE,
             AssetType.THUMBNAIL], start=1
        ):
            ps.add_asset(new_asset(i, atype, "x"))
            ps.update_asset(i, state=AssetState.APPROVED)
        mins = {"image": 1, "animation": 1, "voice": 1, "music": 1, "thumbnail": 1}
        assert ps.check_compile_ready(mins) is False
