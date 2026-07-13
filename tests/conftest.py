"""Test compatibility helpers for third-party HTTP mocks."""

import inspect
from types import SimpleNamespace

import pytest
from aioresponses import core as aioresponses_core


@pytest.fixture(autouse=True)
def add_stream_writer_to_aioresponses_responses(monkeypatch: pytest.MonkeyPatch) -> None:
    """Adapt aioresponses until it supports aiohttp 3.14's response constructor."""
    response_class = aioresponses_core.ClientResponse
    if "stream_writer" not in inspect.signature(response_class).parameters:
        return

    class CompatibleClientResponse(response_class):  # type: ignore[misc, valid-type]
        def __init__(self, *args: object, **kwargs: object) -> None:
            kwargs.setdefault("stream_writer", SimpleNamespace(output_size=0))
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(aioresponses_core, "ClientResponse", CompatibleClientResponse)
