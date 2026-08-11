from pathlib import Path

from typer.testing import CliRunner

from wall_harness.cli import app


def test_serve_starts_local_dashboard(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    spec = tmp_path / "wall.yaml"
    spec.write_text(
        "name: test\ngoal: test\ntopics: [{name: test}]\n"
        "sources: [{url: https://example.com/feed}]\n"
    )
    captured = {}

    def fake_run(application, **options):  # type: ignore[no-untyped-def]
        captured["application"] = application
        captured.update(options)

    monkeypatch.setattr("uvicorn.run", fake_run)
    result = CliRunner().invoke(app, ["serve", str(spec), "--port", "9123"])
    assert result.exit_code == 0
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 9123
    assert captured["application"].title == "Wall"


def test_sync_commands_round_trip_a_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "walls"
    workspace.mkdir()
    (workspace / "wall.yaml").write_text(
        "name: test\ngoal: test\ntopics: [{name: test}]\n"
        "sources: [{url: https://example.com/feed}]\n"
    )
    archive = tmp_path / "backup.wall-sync"
    restored = tmp_path / "restored"
    runner = CliRunner(env={"WALL_SYNC_PASSPHRASE": "correct horse battery staple"})

    exported = runner.invoke(app, ["sync", "export", str(workspace), str(archive)])
    imported = runner.invoke(app, ["sync", "import", str(archive), str(restored)])

    assert exported.exit_code == 0
    assert imported.exit_code == 0
    assert (restored / "wall.yaml").exists()
