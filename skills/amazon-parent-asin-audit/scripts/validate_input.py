#!/usr/bin/env python3
"""Validate and normalize an Amazon parent ASIN audit input file."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

from common import ContractError, dump_json, load_json, normalize_asin, validate_iso_date


MARKETPLACE_RE = re.compile(r"^[A-Z]{2,3}$")
SUPPORTED_LANGUAGES = {"en-US", "zh-CN"}


def normalize_input(data: dict[str, Any]) -> dict[str, Any]:
    if data.get("schema_version") != "1.0":
        raise ContractError("schema_version must be '1.0'")

    marketplace = str(data.get("marketplace", "")).strip().upper()
    if not MARKETPLACE_RE.fullmatch(marketplace):
        raise ContractError("marketplace must be a 2-3 letter uppercase code")

    parent = normalize_asin(data.get("parent_asin"), "parent_asin")
    raw_children = data.get("child_asins", [])
    if not isinstance(raw_children, list):
        raise ContractError("child_asins must be an array")
    children: list[str] = []
    for index, value in enumerate(raw_children):
        asin = normalize_asin(value, f"child_asins[{index}]")
        if asin not in children:
            children.append(asin)
    if parent in children:
        raise ContractError("parent_asin cannot also be a child_asin")

    language = str(data.get("language", "en-US")).strip()
    if language not in SUPPORTED_LANGUAGES:
        raise ContractError("language must be a supported language: en-US or zh-CN")

    report_date = data.get("report_date")
    validate_iso_date(report_date, "report_date")

    publish = data.get("publish", False)
    if not isinstance(publish, bool):
        raise ContractError("publish must be true or false")

    return {
        "schema_version": "1.0",
        "marketplace": marketplace,
        "parent_asin": parent,
        "child_asins": children,
        "language": language,
        "report_date": report_date,
        "publish": publish,
    }


def load_and_validate(path: str | Path) -> dict[str, Any]:
    return normalize_input(load_json(path))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Path to input.json")
    parser.add_argument("--output", help="Optional normalized JSON destination")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = load_and_validate(args.input)
        text = dump_json(result, args.output)
        if not args.output:
            sys.stdout.write(text)
        return 0
    except ContractError as exc:
        print(f"Input validation failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
