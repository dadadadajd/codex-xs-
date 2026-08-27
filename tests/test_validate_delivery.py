import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "amazon-parent-asin-audit" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import render_report  # noqa: E402
import validate_delivery  # noqa: E402


class ValidateDeliveryTests(unittest.TestCase):
    def setUp(self):
        fixtures = ROOT / "tests" / "fixtures"
        self.input_data = json.loads((fixtures / "input.valid.json").read_text(encoding="utf-8"))
        self.evidence = json.loads((fixtures / "evidence.conflicting.json").read_text(encoding="utf-8"))
        self.html = render_report.render(self.input_data, self.evidence)

    def test_accepts_complete_sanitized_delivery(self):
        result = validate_delivery.validate_delivery(self.input_data, self.evidence, self.html)
        self.assertTrue(result["valid"])
        self.assertEqual(result["errors"], [])

    def test_rejects_missing_child(self):
        broken = self.html.replace("B000000002", "missing-child")
        result = validate_delivery.validate_delivery(self.input_data, self.evidence, broken)
        self.assertFalse(result["valid"])
        self.assertIn("MISSING_CHILD_ASIN", result["error_codes"])

    def test_rejects_unresolved_placeholder(self):
        result = validate_delivery.validate_delivery(
            self.input_data,
            self.evidence,
            self.html + "{{UNRESOLVED}}",
        )
        self.assertIn("UNRESOLVED_PLACEHOLDER", result["error_codes"])

    def test_rejects_parent_mismatch(self):
        self.evidence["parent"]["asin"] = "B000000099"
        result = validate_delivery.validate_delivery(self.input_data, self.evidence, self.html)
        self.assertIn("PARENT_ASIN_MISMATCH", result["error_codes"])

    def test_rejects_unexpected_child_in_analysis_scope(self):
        extra = dict(self.evidence["children"][0])
        extra["asin"] = "B000000003"
        extra["sales_series"] = {}
        self.evidence["children"].append(extra)
        result = validate_delivery.validate_delivery(self.input_data, self.evidence, self.html)
        self.assertIn("UNEXPECTED_CHILD_ASIN", result["error_codes"])

    def test_rejects_missing_family_series_period(self):
        broken = self.html.replace(">2026-05<", ">missing-period<")
        result = validate_delivery.validate_delivery(self.input_data, self.evidence, broken)
        self.assertIn("MISSING_FAMILY_SERIES_PERIOD", result["error_codes"])

    def test_rejects_wrong_interface_language(self):
        self.input_data["language"] = "zh-CN"
        result = validate_delivery.validate_delivery(self.input_data, self.evidence, self.html)
        self.assertIn("LANGUAGE_RENDER_MISMATCH", result["error_codes"])

    def test_sensitive_scan_fails_closed(self):
        text = "Authorization: Bearer " + "synthetic-secret-value"
        findings = validate_delivery.scan_sensitive(text)
        self.assertIn("AUTHORIZATION_BEARER", findings)

    def test_sensitive_scan_detects_cookie_header(self):
        text = "Cookie: sessionid=" + "x" * 32
        self.assertIn("COOKIE_HEADER", validate_delivery.scan_sensitive(text))

    def test_sensitive_scan_detects_email_address(self):
        self.assertIn("EMAIL_ADDRESS", validate_delivery.scan_sensitive("seller_email: customer@example.com"))

    def test_sensitive_scan_detects_seller_account_identifier(self):
        text = '{"seller_account_id": "A2EXAMPLE123456"}'
        self.assertIn("SELLER_ACCOUNT_ID", validate_delivery.scan_sensitive(text))

    def test_rejects_child_without_findings_or_actions(self):
        self.evidence["children"][0]["findings"] = []
        self.evidence["children"][0]["actions"] = []
        result = validate_delivery.validate_delivery(self.input_data, self.evidence, self.html)
        self.assertIn("MISSING_CHILD_FINDING", result["error_codes"])
        self.assertIn("MISSING_CHILD_ACTION", result["error_codes"])

    def test_fake_provenance_span_cannot_replace_claim_path(self):
        broken = self.html.replace('data-evidence-path="children[0].price"', 'data-evidence-path="removed"')
        broken += '<span class="provenance" hidden>fake</span>'
        result = validate_delivery.validate_delivery(self.input_data, self.evidence, broken)
        self.assertIn("MISSING_CLAIM_PROVENANCE", result["error_codes"])


if __name__ == "__main__":
    unittest.main()
