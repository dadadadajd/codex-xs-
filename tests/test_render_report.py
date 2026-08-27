import copy
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "amazon-parent-asin-audit" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import render_report  # noqa: E402


class RenderReportTests(unittest.TestCase):
    def setUp(self):
        fixtures = ROOT / "tests" / "fixtures"
        self.input_data = json.loads((fixtures / "input.valid.json").read_text(encoding="utf-8"))
        self.evidence = json.loads((fixtures / "evidence.conflicting.json").read_text(encoding="utf-8"))

    def test_renders_all_required_sections_and_children(self):
        result = render_report.render(self.input_data, self.evidence)
        self.assertIn("<!doctype html>", result.lower())
        for section in [
            "Executive summary",
            "Source status",
            "Parent and child matrix",
            "Market evidence",
            "Keyword comparison",
            "Advertising boundaries",
            "30/60/90-day plan",
            "Limitations",
        ]:
            self.assertIn(section, result)
        for asin in self.input_data["child_asins"]:
            self.assertEqual(result.count(asin), 1)
        self.assertNotRegex(result, r"\{\{[A-Z_]+\}\}")

    def test_escapes_untrusted_evidence(self):
        claim = copy.deepcopy(self.evidence["summary"][0])
        claim["text"] = "<script>alert('x')</script>"
        self.evidence["summary"].append(claim)
        result = render_report.render(self.input_data, self.evidence)
        self.assertNotIn("<script>alert", result)
        self.assertIn("&lt;script&gt;", result)

    def test_renders_full_deduplicated_family_series_once(self):
        result = render_report.render(self.input_data, self.evidence)
        for period in ("2026-05", "2026-06", "2026-07", "2026-08"):
            self.assertEqual(result.count(f">{period}<"), 1)
        self.assertIn("Family demand estimate", result)
        self.assertIn("sorftime", result)

    def test_renders_chinese_interface_for_zh_cn(self):
        input_data = copy.deepcopy(self.input_data)
        input_data["language"] = "zh-CN"
        result = render_report.render(input_data, self.evidence)
        for heading in ["执行摘要", "数据源状态", "父子体矩阵", "市场证据", "广告数据边界", "30/60/90天计划", "局限与待补数据"]:
            self.assertIn(heading, result)
        self.assertNotIn("Executive summary", result)
        self.assertIn("父体销量估算", result)

    def test_links_claims_to_provenance(self):
        result = render_report.render(self.input_data, self.evidence)
        self.assertIn('class="provenance"', result)
        self.assertIn('data-source="amazon-us-live"', result)
        self.assertIn('data-scope="child_asin"', result)
        self.assertIn("2026-08-27T06:00:00Z", result)
        self.assertIn("confirmed live", result)
        self.assertIn('data-evidence-path="children[0].price"', result)


if __name__ == "__main__":
    unittest.main()
