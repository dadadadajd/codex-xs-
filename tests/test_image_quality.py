"""Synthetic pixels only: no customer images, identities or marketplace claims."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/amazon-parent-asin-audit/scripts"
sys.path.insert(0, str(SCRIPTS))

from common import ContractError
import audit_images
import render_report
import validate_delivery


class ImageQualityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.save("sample.png", (600, 450))
        self.manifest = {"schema_version": "1.0", "assets": [{
            "id": "sample", "file": "sample.png", "set_id": "synthetic-set",
            "source_kind": "synthetic", "role": "aplus", "profile": "aplus_mobile",
            "references": [], "expectations": {"display": "95"},
        }]}

    def save(self, name, size, fmt=None, **kwargs):
        image = Image.new("RGB", size, (80, 100, 120))
        image.putpixel((0, 0), (255, 0, 0))
        image.save(self.root / name, format=fmt, **kwargs)

    def audit(self):
        return audit_images.audit(self.manifest, self.root)

    def first(self):
        return self.audit()["assets"][0]

    def codes(self):
        return {c["code"]: c["status"] for c in self.first()["automatic_checks"]}

    def review(self):
        asset = self.first()
        self.manifest["assets"][0]["review"] = {
            "fingerprint": asset["review_fingerprint"], "reviewer": "synthetic-reviewer",
            "reviewed_at": "2026-10-22T09:00:00Z",
            "items": {key: {"status": "pass", "note": "Synthetic test comparison completed."}
                      for key in audit_images.REVIEW_ITEMS},
        }

    def test_exact_size_is_automatic_pass_but_not_visual_approval(self):
        result = self.first()
        self.assertEqual(result["actual"]["size"], [600, 450])
        self.assertEqual(result["actual"]["format"], "PNG")
        self.assertEqual(result["automatic_status"], "pass")
        self.assertEqual(result["status"], "needs_review")
        self.assertTrue(all(x["status"] == "pending" for x in result["visual_review"]))
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_all_requested_profiles(self):
        for profile, size in [("square_2000", (2000, 2000)), ("square_1600", (1600, 1600)),
                              ("aplus_desktop", (1464, 600)), ("aplus_mobile", (600, 450))]:
            with self.subTest(profile=profile):
                self.save("sample.png", size)
                self.manifest["assets"][0]["profile"] = profile
                self.assertEqual(self.first()["automatic_status"], "pass")

    def test_wrong_size_ratio_and_minimum_are_separate_failures(self):
        self.save("sample.png", (300, 300))
        self.manifest["assets"][0]["target"] = {"min_size": [500, 400]}
        codes = self.codes()
        for code in ("TARGET_SIZE", "ASPECT_RATIO", "MIN_RESOLUTION"):
            self.assertEqual(codes[code], "fail")

    def test_ratio_uses_exact_integer_arithmetic(self):
        self.manifest["assets"][0]["profile"] = "four_three"
        self.save("sample.png", (1200, 900))
        self.assertEqual(self.codes()["ASPECT_RATIO"], "pass")
        self.save("sample.png", (1200, 901))
        self.assertEqual(self.codes()["ASPECT_RATIO"], "fail")

    def test_real_format_and_extension_are_checked(self):
        self.save("sample.png", (600, 450), "JPEG")
        self.assertEqual(self.first()["actual"]["format"], "JPEG")
        self.assertEqual(self.codes()["FILE_EXTENSION"], "fail")
        self.save("sample.png", (600, 450), "BMP")
        self.assertEqual(self.codes()["FILE_FORMAT"], "fail")

    def test_missing_corrupt_and_truncated_images_do_not_abort_batch(self):
        self.manifest["assets"].extend([
            {**self.manifest["assets"][0], "id": "missing", "file": "missing.png"},
            {**self.manifest["assets"][0], "id": "corrupt", "file": "corrupt.jpg"},
        ])
        (self.root / "corrupt.jpg").write_bytes(b"not an image")
        result = self.audit()
        self.assertEqual(len(result["assets"]), 3)
        self.assertEqual(result["summary"]["blocked"], 2)
        self.save("truncated.jpg", (600, 450))
        data = (self.root / "truncated.jpg").read_bytes()
        (self.root / "sample.png").write_bytes(data[:len(data)//2])
        self.assertEqual(self.codes()["READABLE_IMAGE"], "fail")

    def test_exif_display_orientation(self):
        exif = Image.Exif()
        exif[274] = 6
        self.save("sample.jpg", (450, 600), exif=exif)
        self.manifest["assets"][0]["file"] = "sample.jpg"
        result = self.first()
        self.assertEqual(result["actual"]["stored_size"], [450, 600])
        self.assertEqual(result["actual"]["size"], [600, 450])
        self.assertEqual(result["automatic_status"], "pass")

    def test_animation_is_not_treated_as_still_image(self):
        frames = [Image.new("RGB", (600, 450), c) for c in ("red", "blue")]
        frames[0].save(self.root / "sample.png", save_all=True, append_images=frames[1:], duration=100)
        self.assertEqual(self.codes()["STATIC_IMAGE"], "fail")

    def test_contract_rejects_ambiguous_targets_and_unsafe_paths(self):
        changes = [
            {"profile": "typo"}, {"file": "../private.png"}, {"file": "/private.png"},
            {"target": {"size": [0, 450]}}, {"target": {"size": [True, 450]}},
            {"target": {"size": [600, 450], "ratio": [1, 1]}},
            {"target": {"formtas": ["PNG"]}}, {"references": ["https://example.com/a.png"]},
            {"source_kind": []}, {"role": {}},
        ]
        for change in changes:
            with self.subTest(change=change):
                manifest = copy.deepcopy(self.manifest)
                manifest["assets"][0].update(change)
                with self.assertRaises(ContractError):
                    audit_images.audit(manifest, self.root)
        self.manifest["assets"].append(copy.deepcopy(self.manifest["assets"][0]))
        with self.assertRaises(ContractError):
            self.audit()

    def test_root_symlink_escape_is_rejected(self):
        (self.root / "escape.png").symlink_to(self.root.parent / "outside.png")
        self.manifest["assets"][0]["file"] = "escape.png"
        with self.assertRaises(ContractError):
            self.audit()

    def test_vertical_extension_preserves_original_pixels(self):
        self.save("original.png", (600, 300))
        with Image.open(self.root / "original.png") as original:
            canvas = Image.new("RGB", (600, 450), (80, 100, 120))
            canvas.paste(original, (0, 75))
            canvas.save(self.root / "sample.png")
        self.manifest["assets"][0]["extension"] = {"source": "original.png", "offset": [0, 75], "axis": "vertical"}
        self.assertEqual(self.codes()["ORIGINAL_REGION"], "pass")
        self.assertEqual(self.first()["status"], "needs_review")
        self.save("sample.png", (600, 450))
        self.assertEqual(self.codes()["ORIGINAL_REGION"], "needs_review")

    def test_extension_cannot_shrink_or_change_vertical_width(self):
        self.save("original.png", (800, 600))
        self.manifest["assets"][0]["extension"] = {"source": "original.png", "offset": [0, 0], "axis": "vertical"}
        self.assertEqual(self.codes()["EXTENSION_GEOMETRY"], "fail")

    def test_missing_reference_never_implies_visual_pass(self):
        self.manifest["assets"][0]["references"] = ["missing.png"]
        self.assertEqual(self.codes()["REFERENCES_AVAILABLE"], "needs_review")
        self.review()
        self.assertEqual(self.first()["status"], "needs_review")

    def test_review_is_bound_to_image_spec_references_and_set(self):
        self.save("reference.png", (100, 100))
        self.manifest["assets"][0]["references"] = ["reference.png"]
        self.review()
        self.assertEqual(self.first()["status"], "pass")
        for name, size in [("sample.png", (600, 450)), ("reference.png", (100, 100))]:
            self.review()
            Image.new("RGB", size, "white").save(self.root / name)
            self.assertEqual(self.first()["status"], "needs_review")
        self.review()
        self.manifest["assets"][0]["expectations"]["display"] = "90"
        self.assertEqual(self.first()["status"], "needs_review")
        self.review()
        self.manifest["assets"].append({**self.manifest["assets"][0], "id": "peer", "review": None})
        self.assertEqual(self.first()["status"], "needs_review")

    def test_manual_failure_needs_action_and_blocks_approval(self):
        self.review()
        item = self.manifest["assets"][0]["review"]["items"]["logo"]
        item.update(status="fail", note="Synthetic badge remains.", recommendation="Remove the synthetic badge.")
        self.assertEqual(self.first()["status"], "blocked")
        del item["recommendation"]
        with self.assertRaises(ContractError):
            self.audit()

    def test_resource_limits_and_optional_byte_limit(self):
        with patch.object(audit_images, "MAX_PIXELS", 10):
            self.assertEqual(self.codes()["READABLE_IMAGE"], "fail")
        with patch.object(audit_images, "MAX_FILE_BYTES", 10):
            self.assertIsNone(self.first()["actual"]["bytes"])
            self.assertEqual(self.codes()["READABLE_IMAGE"], "fail")
        self.manifest["assets"][0]["target"] = {"max_bytes": 10}
        self.assertEqual(self.codes()["FILE_SIZE"], "fail")

    def test_recorded_visual_review_can_resolve_pixel_difference_only(self):
        self.save("original.png", (600, 300))
        self.manifest["assets"][0]["extension"] = {"source": "original.png", "offset": [0, 75], "axis": "vertical"}
        self.assertEqual(self.codes()["ORIGINAL_REGION"], "needs_review")
        self.review()
        self.assertEqual(self.first()["automatic_status"], "needs_review")
        self.assertEqual(self.first()["status"], "pass")
        self.manifest["assets"][0]["review"]["items"]["background_extension"]["status"] = "not_applicable"
        with self.assertRaises(ContractError):
            self.audit()

    def test_directory_inventory_is_recursive_and_does_not_silently_skip_bad_files(self):
        (self.root / "nested").mkdir()
        (self.root / "nested/broken.webp").write_text("synthetic corrupt bytes")
        (self.root / ".hidden").write_text("ignore")
        manifest = audit_images.directory_manifest(self.root, "aplus_mobile", True)
        self.assertEqual(len(manifest["assets"]), 2)
        result = audit_images.audit(manifest, self.root)
        self.assertEqual(result["summary"]["blocked"], 1)
        with self.assertRaises(ContractError):
            audit_images.audit({"schema_version": "1.0", "assets": []}, self.root)

    def test_fixture_batch_contains_explicit_synthetic_failures_and_review_gaps(self):
        result = audit_images.audit_file(ROOT / "tests/fixtures/images.manifest.json")
        self.assertEqual(result["summary"], {"total": 6, "pass": 0, "blocked": 1, "needs_review": 5})
        self.assertTrue(all(a["source_kind"] == "synthetic" for a in result["assets"]))
        self.assertEqual(next(a for a in result["assets"] if a["id"] == "expanded")["automatic_status"], "pass")

    def test_cli_cannot_overwrite_input_and_strict_accepts_completed_review(self):
        self.review()
        manifest = self.root / "manifest.json"
        manifest.write_text(json.dumps(self.manifest))
        command = [sys.executable, str(SCRIPTS / "audit_images.py"), "--manifest", str(manifest)]
        before = (self.root / "sample.png").read_bytes()
        for output in (manifest, self.root / "sample.png"):
            self.assertEqual(subprocess.run(command + ["--output", str(output)], capture_output=True).returncode, 2)
        self.assertEqual((self.root / "sample.png").read_bytes(), before)
        self.assertEqual(subprocess.run(command + ["--output", str(self.root / "result.json"), "--require-approval"], capture_output=True).returncode, 0)

    def test_unreviewed_cli_exit_codes_and_json(self):
        manifest = self.root / "manifest.json"
        manifest.write_text(json.dumps(self.manifest))
        output = self.root / "result.json"
        args = [sys.executable, str(SCRIPTS / "audit_images.py"), "--manifest", str(manifest), "--output", str(output)]
        self.assertEqual(subprocess.run(args, capture_output=True).returncode, 0)
        self.assertEqual(subprocess.run(args + ["--require-approval"], capture_output=True).returncode, 2)
        self.assertEqual(json.loads(output.read_text())["summary"]["needs_review"], 1)

    def test_report_integration_detects_omission_tampering_and_stale_images(self):
        input_data = json.loads((ROOT / "tests/fixtures/input.valid.json").read_text())
        evidence = json.loads((ROOT / "tests/fixtures/evidence.conflicting.json").read_text())
        quality = self.audit()
        html = render_report.render(input_data, evidence, image_quality=quality)
        self.assertIn('id="image-quality"', html)
        self.assertIn("sample.png", html)
        self.assertIn("95", html)
        result = validate_delivery.validate_delivery(input_data, evidence, html, image_quality=quality)
        self.assertTrue(result["valid"])
        self.assertFalse(result["images_approved"])
        strict = validate_delivery.validate_delivery(input_data, evidence, html, image_quality=quality, require_image_approval=True)
        self.assertIn("IMAGES_NOT_APPROVED", strict["error_codes"])
        missing = validate_delivery.validate_delivery(input_data, evidence, html)
        self.assertIn("IMAGE_MANIFEST_REQUIRED", missing["error_codes"])
        broken = html.replace("sample.png", "other.png")
        self.assertIn("IMAGE_REPORT_MISMATCH", validate_delivery.validate_delivery(input_data, evidence, broken, image_quality=quality)["error_codes"])
        self.save("sample.png", (300, 300))
        self.assertIn("IMAGE_REPORT_MISMATCH", validate_delivery.validate_delivery(input_data, evidence, html, image_quality=self.audit())["error_codes"])

    def test_chinese_report_and_untrusted_labels(self):
        input_data = json.loads((ROOT / "tests/fixtures/input.valid.json").read_text())
        evidence = json.loads((ROOT / "tests/fixtures/evidence.conflicting.json").read_text())
        input_data["language"] = "zh-CN"
        self.manifest["assets"][0]["expectations"]["display"] = '<script>alert("x")</script>'
        quality = self.audit()
        html = render_report.render(input_data, evidence, image_quality=quality)
        self.assertIn("人工视觉复核", html)
        self.assertIn("合成测试素材", html)
        self.assertNotIn('<script>alert(', html)
        self.assertTrue(validate_delivery.validate_delivery(input_data, evidence, html, image_quality=quality)["valid"])

    def test_asin_filenames_do_not_break_child_coverage_and_image_notes_are_scanned(self):
        input_data = json.loads((ROOT / "tests/fixtures/input.valid.json").read_text())
        evidence = json.loads((ROOT / "tests/fixtures/evidence.conflicting.json").read_text())
        name = input_data["child_asins"][0] + ".png"
        self.save(name, (600, 450))
        self.manifest["assets"][0]["file"] = name
        quality = self.audit()
        html = render_report.render(input_data, evidence, image_quality=quality)
        self.assertTrue(validate_delivery.validate_delivery(input_data, evidence, html, image_quality=quality)["valid"])
        self.manifest["assets"][0]["expectations"]["contact"] = "person@example.com"
        quality = self.audit()
        html = render_report.render(input_data, evidence, image_quality=quality)
        self.assertIn("SENSITIVE_DATA", validate_delivery.validate_delivery(input_data, evidence, html, image_quality=quality)["error_codes"])


if __name__ == "__main__":
    unittest.main()
