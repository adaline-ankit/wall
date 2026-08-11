import io
import zipfile
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidTag

from wall_harness.models import Item
from wall_harness.state import KnowledgeState
from wall_harness.sync import export_bundle, import_bundle, validate_archive


def make_workspace(path: Path) -> Path:
    path.mkdir()
    spec = path / "frontier.yaml"
    spec.write_text(
        "name: frontier\ngoal: Learn models\ntopics: [{name: models}]\n"
        "sources: [{url: https://example.com/feed}]\n"
    )
    with KnowledgeState(path / ".wall" / "state.db") as state:
        state.remember(
            "frontier",
            [
                Item.create(
                    title="Sparse model",
                    url="https://example.com/item",
                    summary="Architecture",
                    source="test",
                )
            ],
        )
    return spec


def test_encrypted_bundle_round_trips_specs_and_knowledge(tmp_path: Path) -> None:
    workspace = tmp_path / "source"
    make_workspace(workspace)
    archive = tmp_path / "wall.sync"
    destination = tmp_path / "restored"

    export_bundle(workspace, archive, "correct horse battery staple")
    import_bundle(archive, destination, "correct horse battery staple")

    assert archive.read_bytes().startswith(b"WALLSYNC1")
    assert b"Learn models" not in archive.read_bytes()
    assert (destination / "frontier.yaml").exists()
    with KnowledgeState(destination / ".wall" / "state.db") as state:
        item = Item.create(
            title="Sparse model",
            url="https://example.com/item",
            summary="Architecture",
            source="test",
        )
        assert state.novelty("frontier", item) == 0


def test_wrong_passphrase_fails_authentication(tmp_path: Path) -> None:
    workspace = tmp_path / "source"
    make_workspace(workspace)
    archive = tmp_path / "wall.sync"
    export_bundle(workspace, archive, "correct horse battery staple")
    with pytest.raises(InvalidTag):
        import_bundle(archive, tmp_path / "restored", "incorrect password")


def test_import_refuses_to_overwrite_without_force(tmp_path: Path) -> None:
    workspace = tmp_path / "source"
    make_workspace(workspace)
    archive = tmp_path / "wall.sync"
    export_bundle(workspace, archive, "correct horse battery staple")
    destination = tmp_path / "existing"
    destination.mkdir()
    (destination / "keep.yaml").write_text("do not replace")
    with pytest.raises(FileExistsError):
        import_bundle(archive, destination, "correct horse battery staple")
    assert (destination / "keep.yaml").read_text() == "do not replace"


def test_export_refuses_to_replace_an_existing_bundle(tmp_path: Path) -> None:
    workspace = tmp_path / "source"
    make_workspace(workspace)
    archive = tmp_path / "wall.sync"
    archive.write_bytes(b"keep me")
    with pytest.raises(FileExistsError):
        export_bundle(workspace, archive, "correct horse battery staple")
    assert archive.read_bytes() == b"keep me"


def test_force_import_replaces_only_existing_wall_data(tmp_path: Path) -> None:
    workspace = tmp_path / "source"
    make_workspace(workspace)
    archive = tmp_path / "wall.sync"
    export_bundle(workspace, archive, "correct horse battery staple")
    destination = tmp_path / "restored"
    destination.mkdir()
    (destination / "old.yaml").write_text("name: old")
    (destination / "keep.txt").write_text("unrelated")

    import_bundle(
        archive,
        destination,
        "correct horse battery staple",
        force=True,
    )

    assert not (destination / "old.yaml").exists()
    assert (destination / "frontier.yaml").exists()
    assert (destination / "keep.txt").read_text() == "unrelated"


def test_archive_validation_rejects_parent_relative_paths() -> None:
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("manifest.json", "{}")
        archive.writestr("../escape.yaml", "name: escape")
    payload.seek(0)

    with zipfile.ZipFile(payload) as archive, pytest.raises(ValueError, match="Unsafe path"):
        validate_archive(archive)
