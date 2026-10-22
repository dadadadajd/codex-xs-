"""Deterministic, escaped HTML for image audit results; no image decoder dependency."""
from __future__ import annotations

import json

from common import esc


def render_image_quality(result: dict, language: str) -> str:
    zh = language == "zh-CN"
    def label(en: str, cn: str) -> str:
        return cn if zh else en

    statuses = ({"pass": "通过", "fail": "失败", "blocked": "需修改", "pending": "待复核",
                 "needs_review": "待复核", "not_applicable": "不适用"} if zh else
                {"pass": "Pass", "fail": "Fail", "blocked": "Needs correction", "pending": "Pending",
                 "needs_review": "Needs review", "not_applicable": "Not applicable"})
    def badge(status: str) -> str:
        color = "available" if status == "pass" else "unavailable" if status == "not_applicable" else "partial"
        return f'<span class="status {color}">{esc(statuses[status])}</span>'

    def measured(value) -> str:
        if value is None:
            return label("Unavailable", "不可用")
        if isinstance(value, list):
            return " × ".join(esc(v) for v in value)
        return esc(value)

    def rows_table(headers: list, rows: list) -> str:
        return '<div class="table-wrap"><table><thead><tr>' + ''.join(f'<th>{esc(h)}</th>' for h in headers) + '</tr></thead><tbody>' + ''.join(
            '<tr>' + ''.join(f'<td>{c}</td>' for c in row) + '</tr>' for row in rows) + '</tbody></table></div>'

    summary = result["summary"]
    parts = ['<section id="image-quality">', f'<h2>{label("Image and A+ quality audit", "商品图片与A+素材质检")}</h2>',
        '<div class="callout warning">' + label(
            "Automatic checks confirm only file properties and, when provided, original-region pixels. Product accuracy, logos, text and background quality require a recorded visual review. A valid diagnostic report does not approve its images.",
            "自动检测仅验证文件属性及有原图时的原始区域像素。产品外观、Logo、文字和背景质量须单独记录人工视觉复核；诊断报告有效不代表素材获准交付。") + '</div>',
        '<p>' + label("Total", "图片总数") + f': {summary["total"]} · ' + label("Approved", "已通过") + f': {summary["pass"]} · ' + label("Needs correction", "需修改") + f': {summary["blocked"]} · ' + label("Needs review", "待复核") + f': {summary["needs_review"]}</p>']
    for asset in result["assets"]:
        actual = asset["actual"]
        source = {"synthetic": label("Synthetic test asset", "合成测试素材"),
                  "user_supplied": label("User supplied", "用户提供"), "downloaded": label("Downloaded", "下载素材")}[asset["source_kind"]]
        parts.extend([f'<article class="image-audit" data-image-id="{esc(asset["id"])}">',
            f'<h3>{esc(asset["file"])} {badge(asset["status"])}</h3>',
            f'<p>{esc(asset["id"])} · {esc(asset["set_id"])} · {esc(asset["role"])} · {source}</p>',
            f'<p><strong>{label("Actual", "实测")}:</strong> {measured(actual["size"])} px · {measured(actual["format"])} · {measured(actual["bytes"])} bytes',
            f'<br><strong>{label("Stored size / orientation", "存储尺寸 / 方向")}:</strong> {measured(actual["stored_size"])} / {measured(actual["exif_orientation"])}</p>',
            f'<p><strong>{label("Delivery target", "交付要求")}:</strong> {esc(json.dumps(asset["target"], ensure_ascii=False))}</p>',
            f'<p class="muted">SHA-256: {esc(actual["sha256"] or label("Unavailable", "不可用"))}</p>'])
        if asset["expectations"]:
            parts.append('<ul>' + ''.join(f'<li><strong>{esc(k)}:</strong> {esc(v)}</li>' for k, v in sorted(asset["expectations"].items())) + '</ul>')
        if asset["references"]:
            parts.append(f'<p><strong>{label("References", "参考图")}:</strong></p><ul>' + ''.join(
                f'<li>{esc(r["file"])} · {esc(r["error"] or r["sha256"])}</li>' for r in asset["references"]) + '</ul>')
        if asset["extension"]:
            parts.append(f'<p><strong>{label("Extension contract", "扩图要求")}:</strong> {esc(json.dumps(asset["extension"], ensure_ascii=False))}</p>')
        parts.append(f'<h4>{label("Automatic detection", "自动检测")}</h4>')
        parts.append(rows_table([label("Check", "项目"), label("Result", "结果"), label("Observation", "检测说明"), label("Correction", "修改建议")], [
            [esc(c["code"]), badge(c["status"]), esc(c["message"]), esc(c["recommendation"])] for c in asset["automatic_checks"]]))
        parts.append(f'<h4>{label("Manual visual review", "人工视觉复核")}</h4>')
        state = {"not_supplied": label("No review supplied", "尚未提交复核"), "stale": label("Previous review is stale; review again", "历史复核已失效，请重新复核"), "current": label("Recorded review matches current inputs", "复核记录匹配当前素材与要求")}[asset["review_state"]]
        parts.append(f'<p>{state} · {esc(asset["reviewer"] or "—")} · {esc(asset["reviewed_at"] or "—")}</p>')
        parts.append(rows_table([label("Item", "项目"), label("Result", "结果"), label("Review note", "复核记录"), label("Next action", "下一步")], [
            [esc(c["label"]), badge(c["status"]), esc(c["note"]), esc(c["recommendation"])] for c in asset["visual_review"]]))
        parts.append(f'<p class="muted">{label("Review fingerprint", "复核指纹")}: {esc(asset["review_fingerprint"])}</p></article>')
    parts.append('</section>')
    return '\n'.join(parts)
