import json
from pathlib import Path

EXTENSION = Path(__file__).parents[1] / "integrations" / "chrome-extension"


def test_browser_extension_is_a_scoped_manifest_v3_capture_client() -> None:
    manifest = json.loads((EXTENSION / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["manifest_version"] == 3
    assert manifest["action"]["default_popup"] == "popup.html"
    assert manifest["permissions"] == ["activeTab", "storage"]
    assert "https://*/*" in manifest["optional_host_permissions"]
    assert "http://localhost/*" in manifest["optional_host_permissions"]

    popup = (EXTENSION / "popup.js").read_text(encoding="utf-8")
    assert "/api/reading/captures/browser" in popup
    assert '"Authorization"' in popup
    assert "Bearer" in popup
    assert "WALL_APP_PASSWORD" not in popup


def test_browser_extension_documents_private_capture_setup() -> None:
    guide = (EXTENSION / "README.md").read_text(encoding="utf-8")

    assert "WALL_CAPTURE_TOKEN" in guide
    assert "Load unpacked" in guide
    assert "WALL_APP_PASSWORD" in guide
