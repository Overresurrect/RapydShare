"""Checks on the dependency, CI and README files that guard release builds."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _read(name):
    return (ROOT / name).read_text(encoding="utf-8")


def test_unused_packages_are_not_required():
    names = {re.split(r"[\[<>=\s]", line.strip())[0].lower()
             for line in _read("requirements.txt").splitlines()
             if line.strip() and not line.startswith("#")}
    assert "tinyaes" not in names
    assert "python-multipart" not in names


def test_lock_file_is_hashed_and_has_no_tinyaes():
    lock = _read("requirements.lock")
    assert "--hash=sha256:" in lock
    assert "tinyaes" not in lock.lower()


def test_workflow_pins_actions_and_limits_permissions():
    text = _read(".github/workflows/tests.yml")
    uses = re.findall(r"uses:\s*(\S+)(.*)", text)
    assert uses
    for ref, rest in uses:
        assert re.fullmatch(r"[\w./-]+@[0-9a-f]{40}", ref), ref
        assert re.match(r"\s*# v\d+", rest), ref
    assert re.search(r"^permissions:\s*\n\s+contents: read", text, re.M)
    assert "npm audit --omit=dev" in text


def test_readme_matches_the_access_model():
    text = _read("README.md")
    assert "secure" not in text.lower()
    assert "Username/Password" not in text
    assert "access code" in text.lower()
    assert "not encrypted" in text.lower()
    assert "by default" in text.lower() and "Require access code" in text
    assert "Every share is protected" not in text
    assert "--require-hashes -r requirements.lock" in text

