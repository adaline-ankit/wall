from pathlib import Path

WORKFLOW = Path(__file__).parents[1] / ".github" / "workflows" / "daily-refresh.yml"


def test_daily_refresh_workflow_is_opt_in_and_uses_scoped_credentials() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "schedule:" in workflow
    assert "workflow_dispatch:" in workflow
    assert "MARGIN_REFRESH_TOKEN" in workflow
    assert "MARGIN_REFRESH_URL" in workflow
    assert "/api/reading/refresh" in workflow
    assert "WALL_APP_PASSWORD" not in workflow
    assert "Authorization: Bearer" in workflow
    assert "--retry" in workflow
    assert "Check scoped scheduler configuration" in workflow
    assert "needs.configuration.outputs.enabled" in workflow


def test_hosting_guide_explains_the_repository_scheduler_setup() -> None:
    guide = (Path(__file__).parents[1] / "docs" / "hosting.md").read_text(encoding="utf-8")

    assert "MARGIN_REFRESH_TOKEN" in guide
    assert "MARGIN_REFRESH_URL" in guide
    assert "daily-refresh.yml" in guide
