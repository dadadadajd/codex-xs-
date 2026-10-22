#!/usr/bin/env python3
"""Validate a rendered audit report before delivery or publication."""

from __future__ import annotations

import argparse
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from common import ContractError, PLACEHOLDER_RE, dump_json, load_json
from image_quality_report import render_image_quality
from validate_evidence import iter_claims, iter_metrics, validate_evidence
from validate_input import normalize_input


SENSITIVE_PATTERNS = {
    "AUTHORIZATION_BEARER": re.compile(r"authorization\s*:\s*bearer\s+\S+", re.IGNORECASE),
    "COOKIE_HEADER": re.compile(r"\bcookie\s*:\s*[^\r\n]{16,}", re.IGNORECASE),
    "EMAIL_ADDRESS": re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    "JWT": re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    "PRIVATE_KEY": re.compile(r"-----BEGIN(?: [A-Z]+)? PRIVATE KEY-----", re.IGNORECASE),
    "TOKEN_ASSIGNMENT": re.compile(r"\b(?:api[_-]?key|access[_-]?token|secret|jwt)\s*[:=]\s*['\"]?[A-Za-z0-9_./+-]{16,}", re.IGNORECASE),
    "SITES_PROJECT_ID": re.compile(r"\bappgprj_[A-Za-z0-9_-]+\b", re.IGNORECASE),
    "SITES_ARTIFACT_TOKEN": re.compile(r"\bart_v2[A-Za-z0-9_-]*\b", re.IGNORECASE),
    "SELLER_ACCOUNT_ID": re.compile(
        r"['\"]?(?:seller[_-]?account[_-]?id|merchant[_-]?id)['\"]?\s*[:=]\s*['\"]?[A-Z0-9]{10,20}",
        re.IGNORECASE,
    ),
}


def scan_sensitive(text: str) -> list[str]:
    return [name for name, pattern in SENSITIVE_PATTERNS.items() if pattern.search(text)]


class ChildMatrixParser(HTMLParser):
    """Scope child coverage to its matrix, allowing ASINs in creative filenames."""
    def __init__(self):
        super().__init__()
        self.depth = 0
        self.sections = 0
        self.text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "section":
            if self.depth:
                self.depth += 1
            elif dict(attrs).get("id") == "children":
                self.depth = 1
                self.sections += 1

    def handle_endtag(self, tag):
        if tag == "section" and self.depth:
            self.depth -= 1

    def handle_data(self, data):
        if self.depth:
            self.text.append(data)


def validate_delivery(
    input_data: dict[str, Any],
    evidence: dict[str, Any],
    html: str,
    *,
    image_quality: dict | None = None,
    require_image_approval: bool = False,
) -> dict[str, Any]:
    errors: list[str] = []
    error_codes: list[str] = []
    warnings: list[str] = []

    try:
        normalized = normalize_input(input_data)
        evidence_result = validate_evidence(evidence)
        warnings.extend(evidence_result["warnings"])
    except ContractError as exc:
        return {
            "valid": False,
            "error_codes": ["CONTRACT_ERROR"],
            "errors": [str(exc)],
            "warnings": [],
        }

    def add_error(code: str, message: str) -> None:
        if code not in error_codes:
            error_codes.append(code)
        errors.append(message)

    lowered = html.lower()
    if "<!doctype html>" not in lowered or "<title>" not in lowered or "<main" not in lowered:
        add_error("INVALID_HTML_SHELL", "Report must include a doctype, title, and main element.")
    if PLACEHOLDER_RE.search(html):
        add_error("UNRESOLVED_PLACEHOLDER", "Report contains an unresolved template placeholder.")

    if normalized["language"] == "zh-CN":
        if "执行摘要" not in html or "Executive summary" in html:
            add_error("LANGUAGE_RENDER_MISMATCH", "zh-CN report interface is not fully localized.")
    elif "Executive summary" not in html:
        add_error("LANGUAGE_RENDER_MISMATCH", "English report interface heading is missing.")

    evidence_children = [child.get("asin") for child in evidence.get("children", [])]
    child_matrix = ChildMatrixParser()
    child_matrix.feed(html)
    child_text = " ".join(child_matrix.text)
    if evidence.get("parent", {}).get("asin") != normalized["parent_asin"]:
        add_error(
            "PARENT_ASIN_MISMATCH",
            "Evidence parent ASIN does not match the requested parent ASIN.",
        )
    for asin in normalized["child_asins"]:
        if evidence_children.count(asin) != 1:
            add_error("EVIDENCE_CHILD_COVERAGE", f"Evidence must contain child {asin} exactly once.")
        if child_matrix.sections != 1 or child_text.count(asin) != 1:
            add_error("MISSING_CHILD_ASIN", f"Child matrix must contain child {asin} exactly once.")

    for child in evidence.get("children", []):
        asin = child.get("asin", "unknown")
        if not child.get("findings"):
            add_error("MISSING_CHILD_FINDING", f"Child {asin} needs at least one separately reviewable finding.")
        if not child.get("actions"):
            add_error("MISSING_CHILD_ACTION", f"Child {asin} needs at least one separately reviewable action.")

    unexpected_children = sorted(set(evidence_children) - set(normalized["child_asins"]))
    for asin in unexpected_children:
        add_error(
            "UNEXPECTED_CHILD_ASIN",
            f"Evidence contains out-of-scope child {asin}; record discovered children separately.",
        )

    for group in evidence_result["derived"].get("duplicate_child_series", []):
        for point in group.get("series", {}).get("points", []):
            period = str(point.get("period", ""))
            if period and html.count(f">{period}<") != 1:
                add_error(
                    "MISSING_FAMILY_SERIES_PERIOD",
                    f"Deduplicated family series period {period} must appear exactly once.",
                )

    expected_paths = [path for path, _ in iter_metrics(evidence)]
    expected_paths.extend(path for path, _ in iter_claims(evidence))
    expected_paths.extend(
        f"derived.duplicate_child_series[{index}]"
        for index, _ in enumerate(evidence_result["derived"].get("duplicate_child_series", []))
    )
    for path in expected_paths:
        marker = f'data-evidence-path="{path}"'
        if html.count(marker) != 1:
            add_error(
                "MISSING_CLAIM_PROVENANCE",
                f"Rendered report must contain exactly one provenance marker for {path}.",
            )

    for source in evidence.get("sources", []):
        label = str(source.get("source", ""))
        if label and label not in html:
            add_error("MISSING_SOURCE_LABEL", f"Rendered report is missing source label: {label}")

    if image_quality is not None:
        expected = render_image_quality(image_quality, normalized["language"])
        if html.count(expected) != 1 or html.count('id="image-quality"') != 1:
            add_error("IMAGE_REPORT_MISMATCH", "Image section is missing, modified, duplicated or stale; rerender from the current image manifest.")
        if not image_quality["approved"]:
            warnings.append("Image batch contains failures or pending visual reviews; this report does not approve those assets.")
            if require_image_approval:
                add_error("IMAGES_NOT_APPROVED", "Every image must pass automatic checks and current recorded visual review before creative delivery.")
    elif 'id="image-quality"' in html or require_image_approval:
        add_error("IMAGE_MANIFEST_REQUIRED", "Supply --image-manifest to recheck image coverage and current file contents.")

    combined = "\n".join(
        [
            json.dumps(input_data, ensure_ascii=False),
            json.dumps(evidence, ensure_ascii=False),
            json.dumps(image_quality, ensure_ascii=False),
            html,
        ]
    )
    for finding in scan_sensitive(combined):
        add_error("SENSITIVE_DATA", f"Sensitive-data pattern detected: {finding}")

    return {
        "valid": not errors,
        "error_codes": error_codes,
        "errors": errors,
        "warnings": warnings,
        "images_approved": image_quality["approved"] if image_quality is not None else None,
        "checks": {
            "child_count": len(normalized["child_asins"]),
            "source_count": len(evidence.get("sources", [])),
            "unresolved_placeholders": bool(PLACEHOLDER_RE.search(html)),
            "sensitive_findings": scan_sensitive(combined),
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Path to input.json")
    parser.add_argument("--evidence", required=True, help="Path to evidence.json")
    parser.add_argument("--report", required=True, help="Path to report.html")
    parser.add_argument("--output", help="Optional validation.json destination")
    parser.add_argument("--image-manifest", help="Recompute image checks from the current manifest and files")
    parser.add_argument("--image-root", help="Image root (default: manifest's parent)")
    parser.add_argument("--require-image-approval", action="store_true", help="Also block creative delivery for failed/pending images")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = Path(args.report).read_text(encoding="utf-8")
        if args.image_root and not args.image_manifest:
            raise ContractError("--image-root requires --image-manifest")
        image_quality = None
        if args.image_manifest:
            from audit_images import audit_file
            image_quality = audit_file(args.image_manifest, args.image_root)
        result = validate_delivery(load_json(args.input), load_json(args.evidence), report,
                                   image_quality=image_quality, require_image_approval=args.require_image_approval)
        text = dump_json(result, args.output)
        if not args.output:
            sys.stdout.write(text)
        return 0 if result["valid"] else 2
    except (ContractError, OSError) as exc:
        print(f"Delivery validation failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
