"""Typed loader result contracts for the PR-06 dashboard."""

from __future__ import annotations

from typing import Any, Literal, TypedDict


class LoaderOk(TypedDict):
    status: Literal["ok"]
    data: Any
    path: str
    mtime: str


class LoaderMissing(TypedDict):
    status: Literal["missing"]
    reason: str
    commands: list[str]


LoaderResult = LoaderOk | LoaderMissing
