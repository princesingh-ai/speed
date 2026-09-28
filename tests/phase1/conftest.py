import os

# Synthetic test configuration; never reads a developer's secret.
os.environ["SPEED_JWT_SECRET"] = "phase1-tests-only-not-a-deployment-secret"

import pytest
from app.tools.builtin.register import register_builtin_tools
from app.tools.builtin.filesystem_scope import filesystem_scope
from app.security.models import User


@pytest.fixture(autouse=True)
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(filesystem_scope, "workspace", tmp_path)
    (tmp_path / "fixtures").mkdir()
    (tmp_path / "fixtures" / "inspection-report.txt").write_text(
        "Inspection: worn seal. Review before approval.", encoding="utf-8")
    register_builtin_tools()
    return tmp_path


@pytest.fixture
def user():
    return User(id="phase1-owner", username="phase1", password_hash="unused", roles=["admin"])
