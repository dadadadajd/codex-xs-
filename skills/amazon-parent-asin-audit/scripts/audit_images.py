#!/usr/bin/env python3
"""Read-only batch image delivery checks; visual approval is a separate record."""
from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import re
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from common import ContractError, dump_json, load_json, require_list, require_mapping, validate_iso_datetime

# These are delivery presets, not a claim about current Amazon platform rules.
PROFILES = {
    "square_2000": {"size": [2000, 2000], "ratio": [1, 1]},
    "square_1600": {"size": [1600, 1600], "ratio": [1, 1]},
    "aplus_desktop": {"size": [1464, 600], "ratio": [61, 25]},
    "aplus_mobile": {"size": [600, 450], "ratio": [4, 3]},
    "four_three": {"ratio": [4, 3]},
}
REVIEW_ITEMS = {
    "product_appearance": ("Product appearance / 产品外观", "Compare shape, proportions, colors, top panel, grille and display with verified product references. / 对照实拍核对外形、比例、颜色、顶部、网罩和屏显。"),
    "accessories": ("Accessories / 配件结构", "Check remote, attachments, connectors, quantities and assembly against the supplied specification. / 对照规格核对遥控器、附件、连接处、数量和装配结构。"),
    "text_annotations": ("Text and dimensions / 文字与尺寸标注", "Verify every digit, unit, dimension arrow, feature claim and spelling against authoritative specifications. / 逐项核对数字、单位、尺寸箭头、功能文案和拼写。"),
    "logo": ("Logo and unwanted elements / Logo与多余元素", "Inspect the product, remote, reflections and background at 100% for forbidden logos, text and artifacts. / 放大检查产品、遥控器、反光和背景中的禁用Logo、文字和杂物。"),
    "set_consistency": ("Set consistency / 套图一致性", "Compare all images in this set for fonts, tone, composition, product details and accessory consistency; record allowed differences. / 对比同套字体、色调、构图、产品与配件细节，并记录允许的差异。"),
    "background_extension": ("Background extension / 背景扩展", "Compare source and output for stretching, scaling, cropping or moved elements; inspect seams, repeated texture, light and added objects. If no extension is requested, record why not applicable. / 对照原图检查拉伸、缩放、裁切、元素移动、接缝、重复纹理、光照和新增物体；未要求扩图时写明不适用原因。"),
}
MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_PIXELS = 40_000_000
DECODE_FORMATS = ("JPEG", "PNG", "WEBP", "GIF", "BMP", "TIFF")
EXTENSIONS = {"JPEG": {".jpg", ".jpeg", ".jfif"}, "PNG": {".png"}, "WEBP": {".webp"},
              "GIF": {".gif"}, "BMP": {".bmp"}, "TIFF": {".tif", ".tiff"}}


def pillow():
    try:
        from PIL import Image, ImageOps
    except ImportError as exc:
        raise ContractError("Image audit needs Pillow; install the skill's requirements-images.txt.") from exc
    return Image, ImageOps


def fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def text_field(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{name} must be non-empty text")
    return value


def keys(value: dict, allowed: set, name: str) -> None:
    if set(value) - allowed:
        raise ContractError(f"{name} has unknown fields: {', '.join(sorted(set(value) - allowed))}")


def pair(value: Any, name: str, minimum: int = 1) -> list[int]:
    if not isinstance(value, list) or len(value) != 2 or any(type(v) is not int or v < minimum for v in value):
        raise ContractError(f"{name} must contain two integers >= {minimum}")
    return value


def local_path(root: Path, value: Any) -> Path:
    name = text_field(value, "file path")
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or ":" in name or "\\" in name or any(ord(c) < 32 for c in name):
        raise ContractError("Image paths must be relative POSIX paths inside the image root")
    resolved = (root / name).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ContractError("Image path or symlink leaves the image root")
    return resolved


def normalize_manifest(data: dict, root: Path) -> list[dict]:
    require_mapping(data, "image manifest")
    keys(data, {"schema_version", "assets", "notes"}, "image manifest")
    if data.get("schema_version") != "1.0":
        raise ContractError("image manifest schema_version must be 1.0")
    assets = copy.deepcopy(require_list(data.get("assets"), "assets"))
    if not assets:
        raise ContractError("Image manifest must contain at least one asset; an empty batch is not a pass")
    ids = set()
    for asset in assets:
        require_mapping(asset, "asset")
        keys(asset, {"id", "file", "set_id", "source_kind", "role", "profile", "target", "references", "expectations", "extension", "review"}, "asset")
        identifier = text_field(asset.get("id"), "asset.id")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", identifier) or identifier in ids:
            raise ContractError("Asset IDs must be unique safe identifiers (letters, digits, underscores, hyphens)")
        ids.add(identifier)
        local_path(root, asset.get("file"))
        text_field(asset.get("set_id"), "asset.set_id")
        if asset.get("source_kind") not in ("synthetic", "user_supplied", "downloaded"):
            raise ContractError("source_kind must be synthetic, user_supplied or downloaded")
        if asset.get("role") not in ("listing", "aplus", "brand_story", "reference"):
            raise ContractError("role must be listing, aplus, brand_story or reference")
        profile = asset.get("profile")
        if profile is not None and (not isinstance(profile, str) or profile not in PROFILES):
            raise ContractError("Unknown image profile")
        target = copy.deepcopy(PROFILES.get(profile, {}))
        override = require_mapping(asset.get("target", {}), "target")
        keys(override, {"size", "ratio", "min_size", "formats", "max_bytes"}, "target")
        target.update(override)
        for key in ("size", "ratio", "min_size"):
            if key in target:
                pair(target[key], "target." + key)
        if not ("size" in target or "ratio" in target or "min_size" in target):
            raise ContractError("Supply a profile or a target size, ratio or min_size")
        if "size" in target and "ratio" in target:
            w, h = target["size"]
            a, b = target["ratio"]
            if w * b != h * a:
                raise ContractError("Target size and ratio contradict each other")
        if "size" in target and "min_size" in target and any(a < b for a, b in zip(target["size"], target["min_size"])):
            raise ContractError("Target size is below the minimum resolution")
        formats = target.setdefault("formats", ["JPEG", "PNG"])
        if not isinstance(formats, list) or not formats or any(not isinstance(v, str) or v not in DECODE_FORMATS for v in formats):
            raise ContractError("target.formats must contain supported uppercase decoder names")
        if "max_bytes" in target and (type(target["max_bytes"]) is not int or target["max_bytes"] <= 0):
            raise ContractError("target.max_bytes must be a positive integer")
        asset["target"] = target
        references = asset.setdefault("references", [])
        require_list(references, "references")
        for reference in references:
            local_path(root, reference)
        expectations = require_mapping(asset.setdefault("expectations", {}), "expectations")
        for key, value in expectations.items():
            text_field(key, "expectation name")
            text_field(value, "expectation value")
        extension = asset.get("extension")
        if extension is not None:
            require_mapping(extension, "extension")
            keys(extension, {"source", "offset", "axis"}, "extension")
            local_path(root, extension.get("source"))
            pair(extension.get("offset"), "extension.offset", 0)
            if extension.get("axis") not in ("vertical", "any"):
                raise ContractError("extension.axis must be vertical or any")
        review = asset.get("review")
        if review is not None:
            require_mapping(review, "review")
            keys(review, {"fingerprint", "reviewer", "reviewed_at", "items"}, "review")
            if not re.fullmatch(r"[a-f0-9]{64}", str(review.get("fingerprint", ""))):
                raise ContractError("review.fingerprint must be a SHA-256 string from the audit")
            text_field(review.get("reviewer"), "review.reviewer")
            validate_iso_datetime(review.get("reviewed_at"), "review.reviewed_at")
            items = require_mapping(review.get("items"), "review.items")
            keys(items, set(REVIEW_ITEMS), "review.items")
            for key, item in items.items():
                require_mapping(item, "review item")
                keys(item, {"status", "note", "recommendation"}, "review item")
                if item.get("status") not in ("pass", "fail", "not_applicable", "pending"):
                    raise ContractError("Invalid visual review status")
                text_field(item.get("note"), "review item note")
                if "recommendation" in item:
                    text_field(item["recommendation"], "review recommendation")
                if item["status"] == "fail" and not item.get("recommendation"):
                    raise ContractError("Failed visual items need a concrete recommendation")
                if key == "product_appearance" and item["status"] == "not_applicable":
                    raise ContractError("Product appearance cannot be marked not applicable")
                if extension and key == "background_extension" and item["status"] == "not_applicable":
                    raise ContractError("A declared extension requires background review")
    return assets


def read_image(path: Path, *, pixels: bool = False) -> tuple[dict, Any, str | None]:
    """Decode bounded bytes, never expose raw EXIF or local paths. No file writes."""
    Image, ImageOps = pillow()
    metadata = {"sha256": None, "bytes": None, "size": None, "stored_size": None, "format": None,
                "frames": None, "exif_orientation": None}
    try:
        with path.open("rb") as source:
            data = source.read(MAX_FILE_BYTES + 1)
        metadata["bytes"] = len(data)
        if len(data) > MAX_FILE_BYTES:
            metadata["bytes"] = None
            return metadata, None, "FILE_LIMIT"
        metadata["sha256"] = hashlib.sha256(data).hexdigest()
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data), formats=DECODE_FORMATS) as image:
                if image.width * image.height > MAX_PIXELS:
                    return metadata, None, "PIXEL_LIMIT"
                image.verify()
            with Image.open(io.BytesIO(data), formats=DECODE_FORMATS) as image:
                image.load()  # verify() alone does not decode truncated JPEG pixel data.
                metadata.update(format=image.format, stored_size=list(image.size),
                                frames=getattr(image, "n_frames", 1), exif_orientation=image.getexif().get(274, 1))
                oriented = ImageOps.exif_transpose(image)
                metadata["size"] = list(oriented.size)
                decoded = oriented.convert("RGBA") if pixels else None
                oriented.close()
                return metadata, decoded, None
    except FileNotFoundError:
        return metadata, None, "FILE_MISSING"
    except (Image.DecompressionBombWarning, Image.DecompressionBombError):
        return metadata, None, "PIXEL_LIMIT"
    except (OSError, ValueError, SyntaxError, EOFError):
        return metadata, None, "DECODE_ERROR"


def check(code: str, status: str, message: str, recommendation: str = "") -> dict:
    return {"code": code, "status": status, "message": message, "recommendation": recommendation}


def inspect_asset(asset: dict, root: Path) -> dict:
    actual, _, error = read_image(local_path(root, asset["file"]))
    checks = []
    if error:
        checks.append(check("READABLE_IMAGE", "fail", error,
                            "Supply a readable, complete image within 50 MiB / 40 MP; do not resize the product to bypass a delivery constraint. / 提供完整可读且在资源限制内的图片；不要擅自缩放产品。"))
    else:
        checks.append(check("READABLE_IMAGE", "pass", "Full decode succeeded / 完整解码成功"))
        target = asset["target"]
        w, h = actual["size"]
        for key, code, ok, message, action in [
            ("formats", "FILE_FORMAT", actual["format"] in target["formats"], actual["format"], "Export to an allowed format without altering product geometry. / 按允许的格式导出，保持产品几何形状。"),
            (None, "FILE_EXTENSION", Path(asset["file"]).suffix.lower() in EXTENSIONS[actual["format"]], actual["format"], "Match the file extension to the actual encoding; renaming alone cannot convert a format. / 让扩展名与实际编码一致；仅重命名不能转换格式。"),
            (None, "STATIC_IMAGE", actual["frames"] == 1, f"Frames / 帧数: {actual['frames']}", "Export a reviewed still frame. / 导出经过复核的静态图片。"),
            ("size", "TARGET_SIZE", actual["size"] == target.get("size"), f"{w} × {h}; target / 目标: {target.get('size')}", "Rebuild the canvas at the target dimensions. Preserve the product; if the source cannot fit without scaling/cropping, resolve the conflicting requirements first. / 按目标尺寸重建画布并保留产品；原图无法容纳时先解决尺寸约束冲突。"),
            ("ratio", "ASPECT_RATIO", w * target.get("ratio", [w, h])[1] == h * target.get("ratio", [w, h])[0], f"{w}:{h}; target / 目标: {target.get('ratio')}", "Extend the background naturally to the requested ratio; do not stretch, scale or crop the original. / 自然扩展背景至目标比例，禁止拉伸、缩放或裁切原图。"),
            ("min_size", "MIN_RESOLUTION", all(a >= b for a, b in zip([w, h], target.get("min_size", [1, 1]))), f"{w} × {h}; minimum / 最低: {target.get('min_size')}", "Obtain a higher-resolution source; upscaling cannot establish authentic detail. / 获取更高分辨率原始素材；放大不能证明真实细节。"),
            ("max_bytes", "FILE_SIZE", actual["bytes"] <= target.get("max_bytes", MAX_FILE_BYTES), f"Bytes / 字节: {actual['bytes']}", "Re-export within the byte limit while preserving geometry and checking text readability. / 在文件大小限制内重新导出，保留几何形状并复核文字清晰度。"),
        ]:
            if key is None or key in target:
                checks.append(check(code, "pass" if ok else "fail", message, "" if ok else action))
    refs = list(dict.fromkeys(asset["references"] + ([asset["extension"]["source"]] if asset.get("extension") else [])))
    reference_results = []
    for name in refs:
        meta, _, ref_error = read_image(local_path(root, name))
        reference_results.append({"file": name, "sha256": meta["sha256"], "error": ref_error})
    if refs:
        missing = any(ref["error"] for ref in reference_results)
        checks.append(check("REFERENCES_AVAILABLE", "needs_review" if missing else "pass",
                            "One or more references unavailable / 部分参考图不可用" if missing else "Reference images decoded / 参考图可读",
                            "Supply the original reference before approving visual comparisons. / 补齐原始参考图后再确认视觉对比。" if missing else ""))
    extension = asset.get("extension")
    if extension and not error and not any(ref["error"] for ref in reference_results):
        _, original, source_error = read_image(local_path(root, extension["source"]), pixels=True)
        _, output, output_error = read_image(local_path(root, asset["file"]), pixels=True)
        try:
            if source_error or output_error:
                checks.append(check("ORIGINAL_REGION", "needs_review", "Image changed during read / 读取时图片发生变化", "Rerun the audit. / 重新检测。"))
            else:
                x, y = extension["offset"]
                w, h = original.size
                fits = x + w <= output.width and y + h <= output.height
                if extension["axis"] == "vertical":
                    fits = fits and x == 0 and w == output.width
                checks.append(check("EXTENSION_GEOMETRY", "pass" if fits else "fail",
                                    f"Source / 原图: {w} × {h}; offset / 位置: {x}, {y}; axis: {extension['axis']}",
                                    "" if fits else "Choose a canvas that contains the original at 1:1; vertical-only extension must keep the source width. / 画布必须能1:1容纳原图；仅上下扩展时保持原图宽度。"))
                if fits:
                    region = output.crop((x, y, x+w, y+h))
                    equal = region.tobytes() == original.tobytes()
                    region.close()
                    checks.append(check("ORIGINAL_REGION", "pass" if equal else "needs_review",
                                        "Decoded RGBA pixels match / 解码后的原始区域像素一致" if equal else "Original region differs; cause not established / 原始区域像素不同，原因尚未确定",
                                        "" if equal else "Compare against a lossless master. Differences may be compression or editing; inspect scale, crop, position and structure manually. / 对照无损原图，区分压缩与编辑差异，人工核对缩放、裁切、位置和结构。"))
        finally:
            if original is not None:
                original.close()
            if output is not None:
                output.close()
    return {"id": asset["id"], "file": asset["file"], "set_id": asset["set_id"], "role": asset["role"],
            "source_kind": asset["source_kind"], "target": asset["target"], "expectations": asset["expectations"],
            "extension": extension, "actual": actual, "references": reference_results, "automatic_checks": checks}


def audit(manifest: dict, root: str | Path) -> dict:
    root = Path(root).resolve()
    assets = normalize_manifest(manifest, root)
    results = [inspect_asset(asset, root) for asset in assets]
    # Bind review decisions to the exact source files, requirements and set membership.
    contexts = [{"spec": {k: v for k, v in asset.items() if k != "review"},
                 "actual": result["actual"], "references": result["references"]}
                for asset, result in zip(assets, results)]
    for asset, result in zip(assets, results):
        group = sorted((context for context in contexts if context["spec"]["set_id"] == asset["set_id"]),
                       key=lambda context: context["spec"]["id"])
        digest = fingerprint({"version": "1.0", "id": asset["id"], "set": group})
        result["review_fingerprint"] = digest
        review = asset.get("review")
        current = bool(review and review["fingerprint"] == digest)
        result["review_state"] = "current" if current else "stale" if review else "not_supplied"
        result["reviewer"] = review["reviewer"] if current else None
        result["reviewed_at"] = review["reviewed_at"] if current else None
        result["visual_review"] = []
        for key, (label, instruction) in REVIEW_ITEMS.items():
            item = review["items"].get(key) if current else None
            result["visual_review"].append({"id": key, "label": label,
                "status": item["status"] if item else "pending",
                "note": item["note"] if item else "No current recorded review / 尚无有效复核记录",
                "recommendation": item.get("recommendation", "") if item and item["status"] != "pending" else instruction})
        auto_statuses = {c["status"] for c in result["automatic_checks"]}
        visual_statuses = {c["status"] for c in result["visual_review"]}
        result["automatic_status"] = "fail" if "fail" in auto_statuses else "needs_review" if "needs_review" in auto_statuses else "pass"
        reviewed_background = next(c["status"] for c in result["visual_review"] if c["id"] == "background_extension") == "pass"
        unresolved_auto = any(c["status"] == "needs_review" and not (c["code"] == "ORIGINAL_REGION" and reviewed_background)
                              for c in result["automatic_checks"])
        result["status"] = ("blocked" if "fail" in auto_statuses or "fail" in visual_statuses else
                            "needs_review" if "pending" in visual_statuses or unresolved_auto else "pass")
    summary = {"total": len(results), **{key: sum(r["status"] == key for r in results) for key in ("pass", "blocked", "needs_review")}}
    return {"schema_version": "1.0", "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": summary, "approved": summary["pass"] == len(results), "assets": results}


def audit_file(manifest_path: str | Path, root: str | Path | None = None) -> dict:
    path = Path(manifest_path)
    return audit(load_json(path), root or path.parent)


def directory_manifest(directory: Path, profile: str, recursive: bool) -> dict:
    paths = directory.rglob("*") if recursive else directory.glob("*")
    # Include every regular file: an unsupported/corrupt extension must not silently disappear.
    files = sorted(p.relative_to(directory).as_posix() for p in paths if p.is_file() and not any(part.startswith(".") for part in p.relative_to(directory).parts))
    return {"schema_version": "1.0", "assets": [
        {"id": f"image-{index+1:04d}", "file": name, "set_id": "batch", "source_kind": "user_supplied",
         "role": "listing", "profile": profile} for index, name in enumerate(files)]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--manifest")
    source.add_argument("--directory", help="Dedicated input directory; all non-hidden files are checked")
    parser.add_argument("--root", help="Image root (default: manifest's parent)")
    parser.add_argument("--profile", choices=sorted(PROFILES), help="Required for directory batches")
    parser.add_argument("--recursive", action="store_true")
    parser.add_argument("--output", required=True, help="Write result JSON outside the input directory")
    parser.add_argument("--write-manifest", help="Save a directory inventory for later review and report integration")
    parser.add_argument("--require-approval", action="store_true", help="Exit 2 if any automatic failure or visual review remains")
    args = parser.parse_args(argv)
    try:
        if args.directory:
            if not args.profile or args.root:
                raise ContractError("Directory batches require --profile and cannot use --root")
            directory = Path(args.directory).resolve()
            if not directory.is_dir():
                raise ContractError("Input directory does not exist")
            if args.write_manifest and Path(args.write_manifest).resolve() == Path(args.output).resolve():
                raise ContractError("Manifest inventory and result JSON require different output paths")
            for destination in (args.output, args.write_manifest):
                if destination and Path(destination).resolve().is_relative_to(directory):
                    raise ContractError("Write results/manifests outside the input directory")
            manifest = directory_manifest(directory, args.profile, args.recursive)
            result = audit(manifest, directory)
            if args.write_manifest:
                dump_json(manifest, args.write_manifest)
        else:
            if args.profile or args.recursive or args.write_manifest:
                raise ContractError("--profile, --recursive and --write-manifest require --directory")
            manifest = load_json(args.manifest)
            root = Path(args.root) if args.root else Path(args.manifest).parent
            assets = normalize_manifest(manifest, root)
            protected = {Path(args.manifest).resolve()}
            for asset in assets:
                protected.add(local_path(root, asset["file"]))
                protected.update(local_path(root, ref) for ref in asset["references"])
                if asset.get("extension"):
                    protected.add(local_path(root, asset["extension"]["source"]))
            if Path(args.output).resolve() in protected:
                raise ContractError("Audit output must not overwrite the manifest, images or references")
            result = audit(manifest, root)
        dump_json(result, args.output)
        print(json.dumps(result["summary"], ensure_ascii=False))
        return 2 if args.require_approval and not result["approved"] else 0
    except (ContractError, OSError) as exc:
        print(f"Image audit failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
