#!/usr/bin/env python3
"""Validate evidence provenance and detect unsafe ASIN-family aggregation."""

from __future__ import annotations

import argparse
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from common import (
    ContractError,
    dump_json,
    load_json,
    normalize_asin,
    require_list,
    require_mapping,
    validate_iso_datetime,
)


SOURCE_TYPES = {
    "amazon_live",
    "seller_backend",
    "sif",
    "sorftime",
    "user_document",
    "analyst",
}
EVIDENCE_CLASSES = {
    "confirmed_live",
    "backend_confirmed",
    "third_party_estimate",
    "historical_detection",
    "inference",
    "unavailable",
}
SCOPES = {
    "parent_family",
    "child_asin",
    "keyword",
    "competitor",
    "category",
    "campaign",
}
STATUSES = {"available", "partial", "unavailable"}
TOP_LEVEL_FIELDS = {
    "schema_version",
    "captured_at",
    "sources",
    "parent",
    "children",
    "market",
    "keywords",
    "competitors",
    "advertising",
    "listing",
    "summary",
    "actions_30_60_90",
    "limitations",
}


def validate_provenance(record: dict[str, Any], path: str) -> None:
    status = record.get("status")
    if status not in STATUSES:
        raise ContractError(f"{path}.status must be available, partial, or unavailable")
    if record.get("source_type") not in SOURCE_TYPES:
        raise ContractError(f"{path}.source_type is unsupported")
    if not str(record.get("source", "")).strip():
        raise ContractError(f"{path}.source is required")
    expected_classes = {"unavailable"} if status == "unavailable" else EVIDENCE_CLASSES - {"unavailable"}
    if record.get("evidence_class") not in expected_classes:
        raise ContractError(f"{path}.evidence_class is incompatible with status")
    if record.get("scope") not in SCOPES:
        raise ContractError(f"{path}.scope is unsupported")
    if not str(record.get("notes", "")).strip():
        raise ContractError(f"{path}.notes is required")
    if status == "unavailable":
        if record.get("captured_at") is not None:
            raise ContractError(f"{path}.captured_at must be null when unavailable")
    else:
        validate_iso_datetime(record.get("captured_at"), f"{path}.captured_at")


def validate_metric(metric: dict[str, Any], path: str) -> None:
    require_mapping(metric, path)
    status = metric.get("status")
    if status == "unavailable":
        if metric.get("value") is not None:
            raise ContractError(f"{path}: unavailable evidence must have a null value")
        if not str(metric.get("reason", "")).strip():
            raise ContractError(f"{path}: unavailable evidence needs a reason")
        validate_provenance(metric, path)
        return
    value = metric.get("value")
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        raise ContractError(f"{path}.value must be a finite number")
    if not str(metric.get("unit", "")).strip():
        raise ContractError(f"{path}.unit is required")
    validate_provenance(metric, path)


def validate_sales_series(series: dict[str, Any], path: str) -> None:
    require_mapping(series, path)
    if not series:
        return
    status = series.get("status")
    points_value = series.get("points")
    if status == "unavailable":
        if not str(series.get("reason", "")).strip():
            raise ContractError(f"{path}: unavailable evidence needs a reason")
        validate_provenance(series, path)
        if points_value not in (None, []):
            raise ContractError(f"{path}.points must be empty when unavailable")
        return
    validate_provenance(series, path)
    points = require_list(points_value, f"{path}.points")
    if not points:
        raise ContractError(f"{path}.points must not be empty when available")
    if not str(series.get("unit", "")).strip():
        raise ContractError(f"{path}.unit is required")
    seen_periods: set[str] = set()
    for point_index, point in enumerate(points):
        require_mapping(point, f"{path}.points[{point_index}]")
        period = str(point.get("period", "")).strip()
        if not period:
            raise ContractError(f"{path}.points[{point_index}].period is required")
        if period in seen_periods:
            raise ContractError(f"{path}.points[{point_index}].period is duplicated")
        seen_periods.add(period)
        value = point.get("value")
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
            raise ContractError(f"{path}.points[{point_index}].value must be a finite number")


def series_fingerprint(series: dict[str, Any]) -> tuple[tuple[Any, Any], ...]:
    return tuple(sorted(
        (point.get("period"), point.get("value"))
        for point in series.get("points", [])
    ))


def require_non_empty_text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{path} is required")
    return value.strip()


def validate_nested_structure(data: dict[str, Any]) -> None:
    """Fail closed with ContractError before any iterator dereferences nested values."""
    parent = require_mapping(data.get("parent"), "parent")
    if "title" in parent:
        require_mapping(parent["title"], "parent.title")

    market = require_mapping(data.get("market"), "market")
    if "category" in market:
        require_mapping(market["category"], "market.category")
    market_metrics = require_list(market.get("metrics"), "market.metrics")
    for index, metric in enumerate(market_metrics):
        require_mapping(metric, f"market.metrics[{index}]")
        require_non_empty_text(metric.get("name"), f"market.metrics[{index}].name")

    keywords = require_list(data.get("keywords"), "keywords")
    for index, keyword in enumerate(keywords):
        keyword = require_mapping(keyword, f"keywords[{index}]")
        require_non_empty_text(keyword.get("phrase"), f"keywords[{index}].phrase")
        estimates = require_list(keyword.get("estimates"), f"keywords[{index}].estimates")
        for estimate_index, estimate in enumerate(estimates):
            require_mapping(estimate, f"keywords[{index}].estimates[{estimate_index}]")

    competitors = require_list(data.get("competitors"), "competitors")
    for index, competitor in enumerate(competitors):
        competitor = require_mapping(competitor, f"competitors[{index}]")
        require_non_empty_text(competitor.get("segment"), f"competitors[{index}].segment")
        if "price" not in competitor:
            raise ContractError(f"competitors[{index}].price is required")
        require_mapping(competitor["price"], f"competitors[{index}].price")
        if "similarity" not in competitor:
            raise ContractError(f"competitors[{index}].similarity is required")
        require_mapping(competitor["similarity"], f"competitors[{index}].similarity")

    advertising = require_mapping(data.get("advertising"), "advertising")
    observations = require_list(advertising.get("front_end_observations"), "advertising.front_end_observations")
    for index, claim in enumerate(observations):
        require_mapping(claim, f"advertising.front_end_observations[{index}]")
    backend_metrics = require_list(advertising.get("backend_metrics"), "advertising.backend_metrics")
    for index, metric in enumerate(backend_metrics):
        require_mapping(metric, f"advertising.backend_metrics[{index}]")
        require_non_empty_text(metric.get("name"), f"advertising.backend_metrics[{index}].name")

    listing = require_mapping(data.get("listing"), "listing")
    for index, claim in enumerate(require_list(listing.get("findings"), "listing.findings")):
        require_mapping(claim, f"listing.findings[{index}]")

    for index, claim in enumerate(require_list(data.get("summary"), "summary")):
        require_mapping(claim, f"summary[{index}]")

    actions = require_mapping(data.get("actions_30_60_90"), "actions_30_60_90")
    for horizon in ("30", "60", "90"):
        for index, claim in enumerate(require_list(actions.get(horizon), f"actions_30_60_90.{horizon}")):
            require_mapping(claim, f"actions_30_60_90.{horizon}[{index}]")


def detect_duplicate_child_series(children: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[tuple[Any, Any], ...], list[str]] = defaultdict(list)
    series_by_fingerprint: dict[tuple[tuple[Any, Any], ...], dict[str, Any]] = {}
    for index, child in enumerate(children):
        asin = normalize_asin(child.get("asin"), f"children[{index}].asin")
        series = require_mapping(child.get("sales_series", {}), f"children[{index}].sales_series")
        fingerprint = series_fingerprint(series)
        if fingerprint:
            groups[fingerprint].append(asin)
            series_by_fingerprint[fingerprint] = series
    return [
        {"asins": asins, "series": series_by_fingerprint[fingerprint]}
        for fingerprint, asins in groups.items()
        if len(asins) > 1
    ]


def iter_metrics(data: dict[str, Any]) -> Iterable[tuple[str, dict[str, Any]]]:
    for index, child in enumerate(data.get("children", [])):
        if "price" in child:
            yield f"children[{index}].price", child["price"]
    for index, metric in enumerate(data.get("market", {}).get("metrics", [])):
        yield f"market.metrics[{index}]", metric
    for keyword_index, keyword in enumerate(data.get("keywords", [])):
        for estimate_index, estimate in enumerate(keyword.get("estimates", [])):
            yield f"keywords[{keyword_index}].estimates[{estimate_index}]", estimate
    for index, competitor in enumerate(data.get("competitors", [])):
        if "price" in competitor:
            yield f"competitors[{index}].price", competitor["price"]
    for index, metric in enumerate(data.get("advertising", {}).get("backend_metrics", [])):
        yield f"advertising.backend_metrics[{index}]", metric


def iter_claims(data: dict[str, Any]) -> Iterable[tuple[str, dict[str, Any]]]:
    parent = data.get("parent", {})
    if "title" in parent:
        yield "parent.title", parent["title"]
    market = data.get("market", {})
    if "category" in market:
        yield "market.category", market["category"]
    for child_index, child in enumerate(data.get("children", [])):
        for claim_index, claim in enumerate(child.get("findings", [])):
            yield f"children[{child_index}].findings[{claim_index}]", claim
        for claim_index, claim in enumerate(child.get("actions", [])):
            yield f"children[{child_index}].actions[{claim_index}]", claim
    for index, competitor in enumerate(data.get("competitors", [])):
        if "similarity" in competitor:
            yield f"competitors[{index}].similarity", competitor["similarity"]
    for index, claim in enumerate(data.get("advertising", {}).get("front_end_observations", [])):
        yield f"advertising.front_end_observations[{index}]", claim
    for index, claim in enumerate(data.get("listing", {}).get("findings", [])):
        yield f"listing.findings[{index}]", claim
    for index, claim in enumerate(data.get("summary", [])):
        yield f"summary[{index}]", claim
    for horizon in ("30", "60", "90"):
        for index, claim in enumerate(data.get("actions_30_60_90", {}).get(horizon, [])):
            yield f"actions_30_60_90.{horizon}[{index}]", claim


def validate_sources(sources: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    seen: set[str] = set()
    registry: dict[str, dict[str, Any]] = {}
    for index, source in enumerate(sources):
        require_mapping(source, f"sources[{index}]")
        label = str(source.get("source", "")).strip()
        if not label:
            raise ContractError(f"sources[{index}].source is required")
        if label in seen:
            raise ContractError(f"sources[{index}].source is duplicated")
        seen.add(label)
        registry[label] = source
        if source.get("source_type") not in SOURCE_TYPES:
            raise ContractError(f"sources[{index}].source_type is unsupported")
        status = source.get("status")
        if status not in STATUSES:
            raise ContractError(f"sources[{index}].status is unsupported")
        if not str(source.get("notes", "")).strip():
            raise ContractError(f"sources[{index}].notes is required")
        if status == "unavailable":
            if source.get("captured_at") is not None:
                raise ContractError(f"sources[{index}].captured_at must be null when unavailable")
        else:
            validate_iso_datetime(source.get("captured_at"), f"sources[{index}].captured_at")
    return registry


def validate_source_reference(record: dict[str, Any], path: str, registry: dict[str, dict[str, Any]]) -> None:
    label = record.get("source")
    registered = registry.get(label)
    if registered is None:
        raise ContractError(f"{path}.source is not present in the source registry")
    if record.get("source_type") != registered.get("source_type"):
        raise ContractError(f"{path}.source_type does not match source registry")
    if record.get("status") != "unavailable" and registered.get("status") == "unavailable":
        raise ContractError(f"{path}: registered source is unavailable")


def validate_claim(claim: dict[str, Any], path: str, registry: dict[str, dict[str, Any]]) -> None:
    claim = require_mapping(claim, path)
    if not isinstance(claim.get("text"), str) or not claim["text"].strip():
        raise ContractError(f"{path}.text must be a non-empty string")
    if claim.get("status") == "unavailable":
        raise ContractError(f"{path}: a material claim cannot be unavailable")
    validate_provenance(claim, path)
    validate_source_reference(claim, path, registry)


def validate_evidence(data: dict[str, Any]) -> dict[str, Any]:
    unsupported_fields = sorted(set(data) - TOP_LEVEL_FIELDS)
    if unsupported_fields:
        raise ContractError("unsupported top-level fields: " + ", ".join(unsupported_fields))
    if data.get("schema_version") != "1.0":
        raise ContractError("schema_version must be '1.0'")
    validate_iso_datetime(data.get("captured_at"), "captured_at")

    sources = require_list(data.get("sources"), "sources")
    children = require_list(data.get("children"), "children")
    parent = require_mapping(data.get("parent"), "parent")
    require_list(data.get("limitations"), "limitations")
    validate_nested_structure(data)
    normalize_asin(parent.get("asin"), "parent.asin")
    source_registry = validate_sources(sources)

    child_asins: list[str] = []
    for index, child in enumerate(children):
        require_mapping(child, f"children[{index}]")
        asin = normalize_asin(child.get("asin"), f"children[{index}].asin")
        if asin in child_asins:
            raise ContractError(f"children[{index}].asin is duplicated")
        child_asins.append(asin)
        if "price" not in child:
            raise ContractError(f"children[{index}].price is required")
        require_mapping(child["price"], f"children[{index}].price")
        findings = require_list(child.get("findings"), f"children[{index}].findings")
        actions = require_list(child.get("actions"), f"children[{index}].actions")
        for claim_index, claim in enumerate(findings):
            require_mapping(claim, f"children[{index}].findings[{claim_index}]")
        for claim_index, claim in enumerate(actions):
            require_mapping(claim, f"children[{index}].actions[{claim_index}]")
        validate_sales_series(
            require_mapping(child.get("sales_series", {}), f"children[{index}].sales_series"),
            f"children[{index}].sales_series",
        )
        if child.get("sales_series"):
            validate_source_reference(child["sales_series"], f"children[{index}].sales_series", source_registry)

    for path, metric in iter_metrics(data):
        metric_record = require_mapping(metric, path)
        validate_metric(metric_record, path)
        validate_source_reference(metric_record, path, source_registry)

    for path, claim in iter_claims(data):
        validate_claim(require_mapping(claim, path), path, source_registry)

    for index, competitor in enumerate(data.get("competitors", [])):
        normalize_asin(competitor.get("asin"), f"competitors[{index}].asin")

    duplicate_groups = detect_duplicate_child_series(children)
    unique_series: dict[tuple[tuple[Any, Any], ...], dict[str, Any]] = {}
    for child in children:
        series = child.get("sales_series", {})
        fingerprint = series_fingerprint(series)
        if fingerprint:
            unique_series[fingerprint] = series

    warning_codes: list[str] = []
    warnings: list[str] = []
    if duplicate_groups:
        warning_codes.append("DUPLICATE_CHILD_SERIES")
        warnings.append(
            "Identical child sales series detected; treat each duplicated series as one likely parent-family estimate and never sum it across children."
        )

    for keyword in data.get("keywords", []):
        values = {
            estimate.get("value")
            for estimate in keyword.get("estimates", [])
            if estimate.get("status") != "unavailable"
        }
        sources_for_keyword = {
            estimate.get("source")
            for estimate in keyword.get("estimates", [])
            if estimate.get("status") != "unavailable"
        }
        if len(values) > 1 and len(sources_for_keyword) > 1:
            if "CROSS_SOURCE_DIFFERENCE" not in warning_codes:
                warning_codes.append("CROSS_SOURCE_DIFFERENCE")
                warnings.append(
                    "Keyword estimates differ across sources; retain the source-specific values side by side."
                )

    latest_family_sales = None
    if len(unique_series) == 1:
        only_series = next(iter(unique_series.values()))
        points = only_series.get("points", [])
        latest_family_sales = max(points, key=lambda point: point["period"])["value"] if points else None

    return {
        "valid": True,
        "warning_codes": warning_codes,
        "warnings": warnings,
        "derived": {
            "child_count": len(children),
            "family_sales_series_count": len(unique_series),
            "duplicate_child_series": duplicate_groups,
            "latest_family_sales": latest_family_sales,
        },
    }


def load_and_validate(path: str | Path) -> dict[str, Any]:
    return validate_evidence(load_json(path))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", required=True, help="Path to evidence.json")
    parser.add_argument("--output", help="Optional validation JSON destination")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = load_and_validate(args.evidence)
        text = dump_json(result, args.output)
        if not args.output:
            sys.stdout.write(text)
        return 0
    except ContractError as exc:
        print(f"Evidence validation failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
