from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def offline_test_environment(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("orchestra.home._ensure_plugin_deps", lambda base: True)
    monkeypatch.setattr("orchestra.app.list_models", lambda *args, **kwargs: ["a/a", "b/b"])
