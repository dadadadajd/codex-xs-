#!/usr/bin/env python3
"""Shared helpers for the Amazon parent ASIN audit skill."""

from __future__ import annotations

import html
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any


ASIN_RE = re.compile(r"^[A-Z0-9]{10}$")
PLACEHOLDER_RE = re.compile(r"\{\{[A-Z_]+\}\}")


class ContractError(ValueError):
    """Raised when an input or evidence contract is violated."""


def load_json(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ContractError(f"JSON file not found: {source}") from exc
    except json.JSONDecodeError as exc:
        raise ContractError(f"Invalid JSON in {source}: {exc}") from exc
    if not isinstance(data, dict):
        raise ContractError(f"Top-level JSON value must be an object: {source}")
    return data


def dump_json(data: dict[str, Any], path: str | Path | None = None) -> str:
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if path is not None:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text, encoding="utf-8")
    return text


def normalize_asin(value: Any, path: str) -> str:
    asin = str(value or "").strip().upper()
    if not ASIN_RE.fullmatch(asin):
        raise ContractError(f"{path} must be 10 uppercase letters or digits")
    return asin


def validate_iso_datetime(value: Any, path: str, *, allow_null: bool = False) -> None:
    if value is None and allow_null:
        return
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{path} must be a non-empty ISO-8601 timestamp")
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ContractError(f"{path} must be a valid ISO-8601 timestamp") from exc
    if "T" not in value or parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ContractError(f"{path} must include a time and timezone offset")


def validate_iso_date(value: Any, path: str) -> None:
    if not isinstance(value, str):
        raise ContractError(f"{path} must be an ISO date")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ContractError(f"{path} must be a valid ISO date") from exc


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def format_value(value: Any, unit: str | None = None) -> str:
    if value is None:
        return "Unavailable"
    if isinstance(value, float):
        rendered = f"{value:,.2f}".rstrip("0").rstrip(".")
    elif isinstance(value, int):
        rendered = f"{value:,}"
    else:
        rendered = str(value)
    if unit == "USD":
        return f"${rendered}"
    if unit == "percent":
        return f"{rendered}%"
    return f"{rendered} {unit}".strip() if unit else rendered


def require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError(f"{path} must be an object")
    return value


def require_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ContractError(f"{path} must be an array")
    return value
