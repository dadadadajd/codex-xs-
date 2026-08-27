import copy
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "amazon-parent-asin-audit" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import validate_input  # noqa: E402


class ValidateInputTests(unittest.TestCase):
    def setUp(self):
        self.fixture = ROOT / "tests" / "fixtures" / "input.valid.json"
        self.data = json.loads(self.fixture.read_text(encoding="utf-8"))

    def test_loads_valid_input(self):
        result = validate_input.load_and_validate(self.fixture)
        self.assertEqual(result["parent_asin"], "B000000000")
        self.assertEqual(len(result["child_asins"]), 2)
        self.assertFalse(result["publish"])

    def test_normalizes_and_deduplicates_children(self):
        data = copy.deepcopy(self.data)
        data["parent_asin"] = "b000000000"
        data["child_asins"] = ["b000000001", "B000000001", " B000000002 "]
        result = validate_input.normalize_input(data)
        self.assertEqual(result["parent_asin"], "B000000000")
        self.assertEqual(result["child_asins"], ["B000000001", "B000000002"])

    def test_rejects_parent_repeated_as_child(self):
        data = copy.deepcopy(self.data)
        data["child_asins"].append(data["parent_asin"])
        with self.assertRaisesRegex(ValueError, "cannot also be a child"):
            validate_input.normalize_input(data)

    def test_rejects_invalid_asin(self):
        data = copy.deepcopy(self.data)
        data["parent_asin"] = "NOT-ASIN"
        with self.assertRaisesRegex(ValueError, "10 uppercase"):
            validate_input.normalize_input(data)

    def test_rejects_unsupported_report_language(self):
        data = copy.deepcopy(self.data)
        data["language"] = "fr-FR"
        with self.assertRaisesRegex(ValueError, "supported language"):
            validate_input.normalize_input(data)


if __name__ == "__main__":
    unittest.main()
