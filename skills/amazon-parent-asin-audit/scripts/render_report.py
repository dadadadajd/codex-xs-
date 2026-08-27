#!/usr/bin/env python3
"""Render a localized, portable Amazon parent ASIN audit HTML report."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Iterable

from common import ContractError, PLACEHOLDER_RE, esc, format_value, load_json
from validate_evidence import validate_evidence
from validate_input import normalize_input


DEFAULT_TEMPLATE = Path(__file__).resolve().parents[1] / "assets" / "report-template.html"

EN = {
    "eyebrow": "Evidence-backed Amazon audit",
    "title": "{parent} Amazon {marketplace} Parent ASIN Audit",
    "report_date": "Report date", "marketplace": "Marketplace", "parent": "Parent", "captured": "Evidence captured",
    "summary": "Executive summary", "sources": "Source status", "children": "Parent and child matrix",
    "market": "Market evidence", "keywords": "Keyword comparison", "competitors": "Competitor context",
    "advertising": "Advertising boundaries", "listing": "Listing findings", "actions": "30/60/90-day plan",
    "limitations": "Limitations",
    "nav_summary": "Summary", "nav_sources": "Sources", "nav_children": "Variations", "nav_market": "Market",
    "nav_keywords": "Keywords", "nav_competitors": "Competitors", "nav_advertising": "Advertising",
    "nav_listing": "Listing", "nav_actions": "Actions", "nav_limitations": "Limitations",
    "footer": "Generated from structured, source-labelled evidence. Revalidate time-sensitive marketplace facts before execution.",
    "no_evidence": "No evidence supplied.", "unavailable": "Unavailable", "available": "Available", "partial": "Partial",
    "source": "Source", "type": "Type", "status": "Status", "captured_header": "Captured", "boundary": "Boundary",
    "child_asin": "Child ASIN", "variation": "Variation", "live_price": "Live price", "findings": "Findings",
    "actions_header": "Actions", "category": "Category", "metric": "Metric", "value": "Value",
    "evidence_class": "Evidence class", "provenance": "Provenance", "notes": "Notes", "keyword": "Keyword", "estimate": "Estimate",
    "asin": "ASIN", "segment": "Segment", "observed_price": "Observed price", "similarity_boundary": "Similarity boundary",
    "backend_boundary_title": "Backend boundary",
    "backend_boundary_text": "Traffic scores, visible placements, and organic or sponsored ranks do not establish spend, CPC, orders, ACOS, ROAS, or budget.",
    "front_end_observations": "Front-end observations", "backend_metrics": "Backend metrics", "reason_notes": "Reason or notes",
    "horizon": "Horizon", "family_actions": "Family-level actions", "days": "days",
    "observed_parent_title": "Observed parent title",
    "keyword_intro": "Source-specific estimates remain separate; differences are not averaged into a verified figure.",
    "family_guardrail_title": "Family-series guardrail",
    "family_guardrail_text": "Identical child sales series were detected. The complete series is shown once as a likely family-level estimate and is never summed across children.",
    "family_series_title": "Family demand estimate", "period": "Period", "series_value": "Estimate",
    "series_meta": "Source: {source} · Evidence: {evidence_class} · Unit: {unit}",
    "warning_duplicate": "Identical child sales series detected; keep one likely parent-family estimate and never sum it across children.",
    "warning_cross_source": "Keyword estimates differ across sources; retain the source-specific values side by side.",
}

ZH_CN = {
    **EN,
    "eyebrow": "基于证据的 Amazon 链接审计", "title": "{parent} Amazon {marketplace}站 父子ASIN审计",
    "report_date": "报告日期", "marketplace": "站点", "parent": "父ASIN", "captured": "证据采集时间",
    "summary": "执行摘要", "sources": "数据源状态", "children": "父子体矩阵", "market": "市场证据",
    "keywords": "关键词对比", "competitors": "竞品环境", "advertising": "广告数据边界", "listing": "Listing诊断",
    "actions": "30/60/90天计划", "limitations": "局限与待补数据",
    "nav_summary": "摘要", "nav_sources": "数据源", "nav_children": "子体", "nav_market": "市场",
    "nav_keywords": "关键词", "nav_competitors": "竞品", "nav_advertising": "广告", "nav_listing": "Listing",
    "nav_actions": "行动", "nav_limitations": "局限",
    "footer": "本报告由结构化、带来源标签的证据生成。执行前请重新验证价格、库存等时效性信息。",
    "no_evidence": "暂无可用证据。", "unavailable": "不可用", "available": "可用", "partial": "部分可用",
    "source": "来源", "type": "类型", "status": "状态", "captured_header": "采集时间", "boundary": "口径与限制",
    "child_asin": "子ASIN", "variation": "变体", "live_price": "实时价格", "findings": "诊断",
    "actions_header": "行动", "category": "类目", "metric": "指标", "value": "数值", "evidence_class": "证据类型",
    "provenance": "证据来源", "notes": "备注", "keyword": "关键词", "estimate": "估算值", "asin": "ASIN", "segment": "细分",
    "observed_price": "观察价格", "similarity_boundary": "可比性说明", "backend_boundary_title": "后台数据边界",
    "backend_boundary_text": "流量分、可见广告位、自然排名或广告排名不能证明花费、CPC、订单、ACOS、ROAS或预算。",
    "front_end_observations": "前台观察", "backend_metrics": "后台指标", "reason_notes": "原因或备注",
    "horizon": "周期", "family_actions": "父体层行动", "days": "天", "observed_parent_title": "观察到的父体标题",
    "keyword_intro": "不同来源的估算值保持分列，不平均成一个所谓的确认值。",
    "family_guardrail_title": "父体销量防重复规则",
    "family_guardrail_text": "检测到多个子体返回完全相同的销量序列。完整序列仅按一个可能的父体估算展示，禁止按子体求和。",
    "family_series_title": "父体销量估算", "period": "周期", "series_value": "估算值",
    "series_meta": "来源：{source} · 证据类型：{evidence_class} · 单位：{unit}",
    "warning_duplicate": "检测到重复子体销量序列；仅保留一个可能的父体估算，禁止按子体求和。",
    "warning_cross_source": "不同来源的关键词估算存在差异，应保留各自数值并列展示。",
}

EVIDENCE_LABELS = {
    "confirmed_live": {"en": "confirmed live", "zh": "前台实时确认"},
    "backend_confirmed": {"en": "backend confirmed", "zh": "后台确认"},
    "third_party_estimate": {"en": "third-party estimate", "zh": "第三方估算"},
    "historical_detection": {"en": "historical detection", "zh": "历史记录"},
    "inference": {"en": "inference", "zh": "分析推断"},
    "unavailable": {"en": "unavailable", "zh": "不可用"},
}


def labels_for(language: str) -> dict[str, str]:
    return ZH_CN if language == "zh-CN" else EN


def evidence_label(value: Any, language: str) -> str:
    mapping = EVIDENCE_LABELS.get(str(value))
    return mapping["zh" if language == "zh-CN" else "en"] if mapping else str(value or "")


def list_html(items: Iterable[Any], labels: dict[str, str], *, empty: str | None = None) -> str:
    clean = [item for item in items if str(item).strip()]
    if not clean:
        return f'<p class="muted">{esc(empty or labels["no_evidence"])}</p>'
    return "<ul>" + "".join(f"<li>{esc(item)}</li>" for item in clean) + "</ul>"


def table(headers: list[str], rows: list[list[Any]], labels: dict[str, str]) -> str:
    if not rows:
        return f'<p class="muted">{esc(labels["no_evidence"])}</p>'
    head = "".join(f"<th>{esc(header)}</th>" for header in headers)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def status_badge(status: str, labels: dict[str, str]) -> str:
    safe = status if status in {"available", "partial", "unavailable"} else "unavailable"
    return f'<span class="status {safe}">{esc(labels[safe])}</span>'


def metric_value(metric: dict[str, Any], labels: dict[str, str]) -> str:
    return labels["unavailable"] if metric.get("value") is None else format_value(metric.get("value"), metric.get("unit"))


def provenance_html(record: dict[str, Any], path: str, labels: dict[str, str], language: str) -> str:
    source = str(record.get("source", ""))
    scope = str(record.get("scope", ""))
    evidence = evidence_label(record.get("evidence_class"), language)
    captured = record.get("captured_at") or labels["unavailable"]
    status = str(record.get("status", "unavailable"))
    return (
        f'<span class="provenance" data-evidence-path="{esc(path)}" data-source="{esc(source)}" data-scope="{esc(scope)}">'
        f'<strong>{esc(source)}</strong><br>{esc(evidence)}<br>{esc(captured)}<br>'
        f'{esc(scope)} · {esc(labels.get(status, status))}</span>'
    )


def claim_list_html(
    claims: list[dict[str, Any]],
    path_prefix: str,
    labels: dict[str, str],
    language: str,
) -> str:
    if not claims:
        return f'<p class="muted">{esc(labels["no_evidence"])}</p>'
    items = []
    for index, claim in enumerate(claims):
        path = f"{path_prefix}[{index}]"
        items.append(f"<li>{esc(claim.get('text'))}{provenance_html(claim, path, labels, language)}</li>")
    return "<ul>" + "".join(items) + "</ul>"


def render_sources(evidence: dict[str, Any], labels: dict[str, str]) -> str:
    rows = [[
        esc(source.get("source")), esc(source.get("source_type")), status_badge(str(source.get("status", "unavailable")), labels),
        esc(source.get("captured_at") or labels["unavailable"]), esc(source.get("notes", "")),
    ] for source in evidence.get("sources", [])]
    return table([labels["source"], labels["type"], labels["status"], labels["captured_header"], labels["boundary"]], rows, labels)


def render_children(evidence: dict[str, Any], labels: dict[str, str], language: str) -> str:
    rows = []
    for index, child in enumerate(evidence.get("children", [])):
        rows.append([
            f"<strong>{esc(child.get('asin'))}</strong>", esc(child.get("label", "")),
            esc(metric_value(child.get("price", {}), labels)), provenance_html(child.get("price", {}), f"children[{index}].price", labels, language),
            claim_list_html(child.get("findings", []), f"children[{index}].findings", labels, language),
            claim_list_html(child.get("actions", []), f"children[{index}].actions", labels, language),
        ])
    return table([labels["child_asin"], labels["variation"], labels["live_price"], labels["provenance"], labels["findings"], labels["actions_header"]], rows, labels)


def render_family_series(validation: dict[str, Any], labels: dict[str, str], language: str) -> str:
    blocks = []
    for index, group in enumerate(validation["derived"].get("duplicate_child_series", [])):
        series = group.get("series", {})
        rows = [[esc(point.get("period")), esc(format_value(point.get("value"), series.get("unit")))] for point in series.get("points", [])]
        meta = labels["series_meta"].format(source=series.get("source", ""), evidence_class=evidence_label(series.get("evidence_class"), language), unit=series.get("unit", ""))
        blocks.append(
            f'<h3>{esc(labels["family_series_title"])}</h3><p class="muted">{esc(meta)}</p>'
            + provenance_html(series, f"derived.duplicate_child_series[{index}]", labels, language)
            + table([labels["period"], labels["series_value"]], rows, labels)
        )
    return "".join(blocks)


def render_market(evidence: dict[str, Any], validation: dict[str, Any], labels: dict[str, str], language: str) -> str:
    market = evidence.get("market", {})
    rows = [[
        esc(metric.get("name")), esc(metric_value(metric, labels)),
        provenance_html(metric, f"market.metrics[{index}]", labels, language), esc(metric.get("notes", "")),
    ] for index, metric in enumerate(market.get("metrics", []))]
    warning = ""
    if "DUPLICATE_CHILD_SERIES" in validation["warning_codes"]:
        warning = f'<div class="callout warning"><strong>{esc(labels["family_guardrail_title"])}:</strong> {esc(labels["family_guardrail_text"])}</div>'
        warning += render_family_series(validation, labels, language)
    category_claim = market.get("category", {})
    category = (
        f"<p><strong>{esc(labels['category'])}:</strong> {esc(category_claim.get('text', labels['unavailable']))}</p>"
        + provenance_html(category_claim, "market.category", labels, language)
    )
    return category + warning + table([labels["metric"], labels["value"], labels["provenance"], labels["notes"]], rows, labels)


def render_keywords(evidence: dict[str, Any], labels: dict[str, str], language: str) -> str:
    rows = []
    for keyword_index, keyword in enumerate(evidence.get("keywords", [])):
        for estimate_index, estimate in enumerate(keyword.get("estimates", [])):
            rows.append([
                esc(keyword.get("phrase", "")), esc(metric_value(estimate, labels)),
                provenance_html(estimate, f"keywords[{keyword_index}].estimates[{estimate_index}]", labels, language),
                esc(estimate.get("notes", "")),
            ])
    return f'<div class="callout">{esc(labels["keyword_intro"])}</div>' + table(
        [labels["keyword"], labels["estimate"], labels["provenance"], labels["notes"]], rows, labels
    )


def render_competitors(evidence: dict[str, Any], labels: dict[str, str], language: str) -> str:
    rows = []
    for index, competitor in enumerate(evidence.get("competitors", [])):
        price = competitor.get("price", {})
        similarity = competitor.get("similarity", {})
        rows.append([
            esc(competitor.get("asin")), esc(competitor.get("segment", "")), esc(metric_value(price, labels)),
            provenance_html(price, f"competitors[{index}].price", labels, language),
            esc(similarity.get("text", "")) + provenance_html(similarity, f"competitors[{index}].similarity", labels, language),
        ])
    return table([labels["asin"], labels["segment"], labels["observed_price"], labels["provenance"], labels["similarity_boundary"]], rows, labels)


def render_advertising(evidence: dict[str, Any], labels: dict[str, str], language: str) -> str:
    advertising = evidence.get("advertising", {})
    rows = [[
        esc(metric.get("name")), esc(metric_value(metric, labels)), status_badge(str(metric.get("status", "unavailable")), labels),
        provenance_html(metric, f"advertising.backend_metrics[{index}]", labels, language), esc(metric.get("reason") or metric.get("notes", "")),
    ] for index, metric in enumerate(advertising.get("backend_metrics", []))]
    boundary = f'<div class="callout warning"><strong>{esc(labels["backend_boundary_title"])}:</strong> {esc(labels["backend_boundary_text"])}</div>'
    return boundary + f'<h3>{esc(labels["front_end_observations"])}</h3>' + claim_list_html(
        advertising.get("front_end_observations", []), "advertising.front_end_observations", labels, language
    ) + f'<h3>{esc(labels["backend_metrics"])}</h3>' + table(
        [labels["metric"], labels["value"], labels["status"], labels["provenance"], labels["reason_notes"]], rows, labels
    )


def render_actions(evidence: dict[str, Any], labels: dict[str, str], language: str) -> str:
    actions = evidence.get("actions_30_60_90", {})
    rows = [[
        f"<strong>{horizon} {esc(labels['days'])}</strong>",
        claim_list_html(actions.get(horizon, []), f"actions_30_60_90.{horizon}", labels, language),
    ] for horizon in ("30", "60", "90")]
    return table([labels["horizon"], labels["family_actions"]], rows, labels)


def replace_template(template: str, sections: dict[str, str]) -> str:
    rendered = template
    for key, value in sections.items():
        rendered = rendered.replace("{{" + key + "}}", value)
    unresolved = PLACEHOLDER_RE.findall(rendered)
    if unresolved:
        raise ContractError("unresolved report template placeholder: " + ", ".join(sorted(set(unresolved))))
    return rendered


def localized_warnings(codes: list[str], labels: dict[str, str]) -> list[str]:
    mapping = {"DUPLICATE_CHILD_SERIES": labels["warning_duplicate"], "CROSS_SOURCE_DIFFERENCE": labels["warning_cross_source"]}
    return [mapping[code] for code in codes if code in mapping]


def render(input_data: dict[str, Any], evidence: dict[str, Any], template_path: str | Path | None = None) -> str:
    normalized = normalize_input(input_data)
    validation = validate_evidence(evidence)
    language = normalized["language"]
    labels = labels_for(language)
    parent = evidence.get("parent", {})
    title = labels["title"].format(parent=normalized["parent_asin"], marketplace=normalized["marketplace"])
    meta = "".join([
        f"<span>{esc(labels['report_date'])}: {esc(normalized['report_date'])}</span>",
        f"<span>{esc(labels['marketplace'])}: {esc(normalized['marketplace'])}</span>",
        f"<span>{esc(labels['parent'])}: {esc(normalized['parent_asin'])}</span>",
        f"<span>{esc(labels['captured'])}: {esc(evidence.get('captured_at'))}</span>",
    ])
    summary = claim_list_html(evidence.get("summary", []), "summary", labels, language)
    warnings = localized_warnings(validation["warning_codes"], labels)
    if warnings:
        summary += '<div class="callout warning">' + list_html(warnings, labels) + "</div>"
    listing = claim_list_html(evidence.get("listing", {}).get("findings", []), "listing.findings", labels, language)
    title_claim = parent.get("title", {})
    if title_claim:
        listing = (
            f"<p><strong>{esc(labels['observed_parent_title'])}:</strong> {esc(title_claim.get('text'))}</p>"
            + provenance_html(title_claim, "parent.title", labels, language)
            + listing
        )

    template = (Path(template_path) if template_path else DEFAULT_TEMPLATE).read_text(encoding="utf-8")
    sections = {
        "LANG": esc(language), "TITLE": esc(title), "EYEBROW": esc(labels["eyebrow"]), "REPORT_META": meta,
        "EXECUTIVE_SUMMARY": summary, "SOURCE_STATUS": render_sources(evidence, labels),
        "CHILD_MATRIX": render_children(evidence, labels, language), "MARKET": render_market(evidence, validation, labels, language),
        "KEYWORDS": render_keywords(evidence, labels, language), "COMPETITORS": render_competitors(evidence, labels, language),
        "ADVERTISING": render_advertising(evidence, labels, language), "LISTING": listing,
        "ACTIONS": render_actions(evidence, labels, language), "LIMITATIONS": list_html(evidence.get("limitations", []), labels),
        "FOOTER": esc(labels["footer"]),
    }
    for key in ("summary", "sources", "children", "market", "keywords", "competitors", "advertising", "listing", "actions", "limitations"):
        sections["H_" + key.upper()] = esc(labels[key])
        sections["NAV_" + key.upper()] = esc(labels["nav_" + key])
    return replace_template(template, sections)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Path to input.json")
    parser.add_argument("--evidence", required=True, help="Path to evidence.json")
    parser.add_argument("--output", required=True, help="Destination report.html")
    parser.add_argument("--template", help="Optional custom template path")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        rendered = render(load_json(args.input), load_json(args.evidence), args.template)
        destination = Path(args.output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(rendered, encoding="utf-8")
        print(f"Rendered report: {destination}")
        return 0
    except (ContractError, OSError) as exc:
        print(f"Report rendering failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
