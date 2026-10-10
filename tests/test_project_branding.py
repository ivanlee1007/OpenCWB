"""Public project branding must not break persisted integration identity."""
import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "opencwb"
BRAND = "Uninus OpenCWA"
REPO = "https://github.com/ivanlee1007/Uninus-OpenCWA"


def test_public_brand_and_persisted_domain():
    manifest = json.loads((COMPONENT / "manifest.json").read_text(encoding="utf-8"))
    hacs = json.loads((ROOT / "hacs.json").read_text(encoding="utf-8"))
    assert manifest["name"] == BRAND
    assert hacs["name"] == BRAND
    assert manifest["domain"] == hacs["domain"] == "opencwb"
    assert manifest["documentation"] == hacs["documentation"] == REPO
    assert manifest["issue_tracker"] == hacs["issue_tracker"] == REPO + "/issues"
    constants = {}
    for node in ast.parse((COMPONENT / "const.py").read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    constants[target.id] = node.value.value
    assert constants["DOMAIN"] == "opencwb"
    assert constants["DEFAULT_NAME"] == BRAND
    for path in [COMPONENT / "strings.json", *sorted((COMPONENT / "translations").glob("*.json"))]:
        translation = json.loads(path.read_text(encoding="utf-8"))
        assert translation["config"]["step"]["user"]["title"] == BRAND
        assert "OpenCWB" not in path.read_text(encoding="utf-8")
    for name in ["README.md", "README_zh-tw.md"]:
        readme = (ROOT / name).read_text(encoding="utf-8")
        assert readme.startswith("# " + BRAND + "\n")
        assert "URL: `" + REPO + "`" in readme
        assert "tsunglung/Uninus" not in readme
        assert "`opencwb`" in readme
        assert "tsunglung/OpenCWB/blob" not in readme
