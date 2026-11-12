"""Pytest configuration: hardware tests are opt-in and never run in CI."""

from __future__ import annotations

import os

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    live = os.environ.get("LITEARM_LIVE") == "1"
    live_writes = os.environ.get("LITEARM_LIVE_WRITES") == "1"
    for item in items:
        if item.get_closest_marker("live") is None:
            continue
        if not live:
            item.add_marker(pytest.mark.skip(reason="set LITEARM_LIVE=1 to run hardware tests"))
        elif item.get_closest_marker("live_write") is not None and not live_writes:
            item.add_marker(
                pytest.mark.skip(reason="set LITEARM_LIVE_WRITES=1 to run write tests")
            )
