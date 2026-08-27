import copy
import json
import math
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "amazon-parent-asin-audit" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import validate_evidence  # noqa: E402


class ValidateEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.fixture = ROOT / "tests" / "fixtures" / "evidence.conflicting.json"
        self.data = json.loads(self.fixture.read_text(encoding="utf-8"))

    def test_duplicate_child_series_is_family_scoped(self):
        result = validate_evidence.load_and_validate(self.fixture)
        self.assertIn("DUPLICATE_CHILD_SERIES", result["warning_codes"])
        self.assertEqual(result["derived"]["family_sales_series_count"], 1)
        self.assertEqual(result["derived"]["latest_family_sales"], 20)
        self.assertNotEqual(result["derived"]["latest_family_sales"], 40)

    def test_unavailable_metric_cannot_be_zero(self):
        bad = {
            "status": "unavailable",
            "value": 0,
            "reason": "not connected",
        }
        with self.assertRaisesRegex(ValueError, "null value"):
            validate_evidence.validate_metric(bad, "advertising.acos")

    def test_unavailable_metric_needs_reason(self):
        bad = {"status": "unavailable", "value": None}
        with self.assertRaisesRegex(ValueError, "needs a reason"):
            validate_evidence.validate_metric(bad, "advertising.acos")

    def test_unavailable_metric_still_needs_provenance(self):
        bad = {
            "status": "unavailable",
            "value": None,
            "reason": "not connected",
            "evidence_class": "unavailable",
            "scope": "campaign",
            "captured_at": None,
        }
        with self.assertRaisesRegex(ValueError, "source_type"):
            validate_evidence.validate_metric(bad, "advertising.acos")

    def test_unavailable_source_cannot_claim_a_capture_time(self):
        data = copy.deepcopy(self.data)
        unavailable = next(source for source in data["sources"] if source["status"] == "unavailable")
        unavailable["captured_at"] = "2026-08-27T06:03:00Z"
        with self.assertRaisesRegex(ValueError, "must be null"):
            validate_evidence.validate_evidence(data)

    def test_available_metric_requires_provenance(self):
        metric = copy.deepcopy(self.data["children"][0]["price"])
        del metric["captured_at"]
        with self.assertRaisesRegex(ValueError, "captured_at"):
            validate_evidence.validate_metric(metric, "children.0.price")

    def test_keyword_conflict_remains_two_estimates(self):
        result = validate_evidence.validate_evidence(self.data)
        self.assertIn("CROSS_SOURCE_DIFFERENCE", result["warning_codes"])
        self.assertEqual(len(self.data["keywords"][0]["estimates"]), 2)

    def test_parent_asin_is_validated(self):
        data = copy.deepcopy(self.data)
        data["parent"]["asin"] = "wrong"
        with self.assertRaisesRegex(ValueError, "parent.asin"):
            validate_evidence.validate_evidence(data)

    def test_metric_value_must_be_finite_numeric(self):
        for bad_value in ("not-a-number", math.nan, math.inf):
            metric = copy.deepcopy(self.data["children"][0]["price"])
            metric["value"] = bad_value
            with self.subTest(bad_value=bad_value), self.assertRaisesRegex(ValueError, "finite number"):
                validate_evidence.validate_metric(metric, "children[0].price")

    def test_available_metric_requires_notes_and_unit(self):
        metric = copy.deepcopy(self.data["children"][0]["price"])
        metric["notes"] = ""
        with self.assertRaisesRegex(ValueError, "notes"):
            validate_evidence.validate_metric(metric, "children[0].price")
        metric = copy.deepcopy(self.data["children"][0]["price"])
        metric["unit"] = ""
        with self.assertRaisesRegex(ValueError, "unit"):
            validate_evidence.validate_metric(metric, "children[0].price")

    def test_metric_source_must_match_registered_source(self):
        data = copy.deepcopy(self.data)
        data["children"][0]["price"]["source_type"] = "sif"
        with self.assertRaisesRegex(ValueError, "does not match source registry"):
            validate_evidence.validate_evidence(data)

    def test_available_metric_cannot_use_unavailable_source(self):
        data = copy.deepcopy(self.data)
        price = data["children"][0]["price"]
        price["source"] = "amazon-ads-backend"
        price["source_type"] = "seller_backend"
        with self.assertRaisesRegex(ValueError, "registered source is unavailable"):
            validate_evidence.validate_evidence(data)

    def test_competitor_price_requires_metric_provenance(self):
        data = copy.deepcopy(self.data)
        data["competitors"][0]["price"] = 209.99
        with self.assertRaisesRegex(ValueError, r"competitors\[0\]\.price must be an object"):
            validate_evidence.validate_evidence(data)

    def test_timestamp_requires_time_and_timezone(self):
        for bad_timestamp in ("2026-08-27", "2026-08-27T06:00:00"):
            data = copy.deepcopy(self.data)
            data["captured_at"] = bad_timestamp
            with self.subTest(timestamp=bad_timestamp), self.assertRaisesRegex(ValueError, "timezone"):
                validate_evidence.validate_evidence(data)

    def test_plain_text_material_claim_is_rejected(self):
        data = copy.deepcopy(self.data)
        data["children"][0]["findings"] = ["Motor is 500W"]
        with self.assertRaisesRegex(ValueError, r"children\[0\]\.findings\[0\] must be an object"):
            validate_evidence.validate_evidence(data)

    def test_malformed_market_is_a_contract_error(self):
        data = copy.deepcopy(self.data)
        data["market"] = []
        with self.assertRaisesRegex(ValueError, "market must be an object"):
            validate_evidence.validate_evidence(data)

    def test_malformed_keyword_and_competitor_are_contract_errors(self):
        data = copy.deepcopy(self.data)
        data["keywords"] = ["bad"]
        with self.assertRaisesRegex(ValueError, r"keywords\[0\] must be an object"):
            validate_evidence.validate_evidence(data)

        data = copy.deepcopy(self.data)
        data["competitors"] = ["price"]
        with self.assertRaisesRegex(ValueError, r"competitors\[0\] must be an object"):
            validate_evidence.validate_evidence(data)

    def test_child_price_must_be_explicit_even_when_unavailable(self):
        data = copy.deepcopy(self.data)
        del data["children"][0]["price"]
        with self.assertRaisesRegex(ValueError, r"children\[0\]\.price is required"):
            validate_evidence.validate_evidence(data)

    def test_unknown_top_level_fields_are_rejected(self):
        data = copy.deepcopy(self.data)
        data["seller_account_id"] = "A2EXAMPLE123456"
        with self.assertRaisesRegex(ValueError, "unsupported top-level fields"):
            validate_evidence.validate_evidence(data)

    def test_metric_name_and_keyword_phrase_are_required(self):
        data = copy.deepcopy(self.data)
        del data["market"]["metrics"][0]["name"]
        with self.assertRaisesRegex(ValueError, r"market\.metrics\[0\]\.name is required"):
            validate_evidence.validate_evidence(data)

        data = copy.deepcopy(self.data)
        data["keywords"][0]["phrase"] = ""
        with self.assertRaisesRegex(ValueError, r"keywords\[0\]\.phrase is required"):
            validate_evidence.validate_evidence(data)

    def test_duplicate_series_detection_is_order_independent(self):
        data = copy.deepcopy(self.data)
        data["children"][1]["sales_series"]["points"].reverse()
        result = validate_evidence.validate_evidence(data)
        self.assertIn("DUPLICATE_CHILD_SERIES", result["warning_codes"])
        self.assertEqual(result["derived"]["family_sales_series_count"], 1)
        self.assertEqual(result["derived"]["latest_family_sales"], 20)


if __name__ == "__main__":
    unittest.main()
