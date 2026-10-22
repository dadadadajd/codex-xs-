# Image and A+ Quality Contract

## Contents

- Scope and installation
- Batch manifest and delivery presets
- Automated checks and limits
- Visual review and approval
- Report integration and release gates
- Synthetic fixtures

## Scope and installation

Use this module for Listing, A+ and brand-story still images. It is read-only:
it does not resize, compress, crop, remove logos or invent corrected assets.
Videos remain part of the existing Listing review workflow. These dimensions
are user delivery targets, not a statement of current Amazon marketplace rules.
Check the applicable marketplace/module rules separately if compliance is requested.

From the skill directory, install the optional image decoder:

```sh
python -m pip install -r requirements-images.txt
```

The existing non-image workflow still uses only the standard library. The
image audit uses Pillow to verify and fully decode files rather than trusting
extensions or headers alone. No network, API key or OCR service is required.

## Batch manifest and delivery presets

Create `images.json` separately from `input.json` and `evidence.json`:

```json
{
  "schema_version": "1.0",
  "assets": [{
    "id": "heater-mobile-01",
    "file": "assets/mobile.png",
    "set_id": "heater-silver",
    "source_kind": "user_supplied",
    "role": "aplus",
    "profile": "aplus_mobile",
    "references": ["references/product.png", "references/remote.png"],
    "expectations": {
      "spec_source": "User-approved product specification, revision 2",
      "display": "95",
      "color": "Silver top, black grille",
      "accessories": "One remote, same button layout as reference",
      "forbidden_elements": "Garvee logo and unwanted promotional text",
      "dimensions": "Copy only from the approved dimension drawing",
      "style": "Match the approved set's fonts, warm tone and composition"
    },
    "extension": {"source": "references/original.png", "offset": [0, 75], "axis": "vertical"}
  }]
}
```

All paths are relative to the manifest's directory, or explicit `--root` /
`--image-root`. Absolute paths, URLs, traversal and symlinks escaping that root
are rejected. IDs must be unique. Missing/corrupt asset files become per-image
failures; malformed manifests stop the batch with exit 2. Unknown fields fail
validation so a misspelled requirement cannot silently disappear.

| Field | Contract |
|---|---|
| `id`, `file`, `set_id` | Required; use opaque, non-personal IDs and paths |
| `source_kind` | Required: `synthetic`, `user_supplied`, `downloaded`; this is an input label, not proof of authenticity |
| `role` | Required: `listing`, `aplus`, `brand_story`, `reference` |
| `profile` | Optional named delivery preset below |
| `target` | Optional overrides: `size`, `ratio`, `min_size` (two positive integers each), `formats`, `max_bytes` |
| `references` | Optional list of local reference paths; missing references prevent approval |
| `expectations` | Optional string-to-string map of authoritative product/text/style requirements and source notes |
| `extension` | Optional original path, nonnegative `[x,y]` offset and `vertical` or `any` axis; coordinates use EXIF-oriented pixels |
| `review` | Optional recorded visual decisions, described below |

| Profile | Exact width × height | Ratio |
|---|---|---|
| `square_2000` | 2000 × 2000 | 1:1 |
| `square_1600` | 1600 × 1600 | 1:1 |
| `aplus_desktop` | 1464 × 600 | 61:25 |
| `aplus_mobile` | 600 × 450 | 4:3 |
| `four_three` | No fixed pixel dimensions | 4:3 |

Default allowed formats are PNG and JPEG. Supply a custom target for other
sizes, such as `{"size":[362,453],"formats":["PNG"]}`. A profile's values and
overrides must agree: changing its size without changing an incompatible ratio
is rejected. Ratios use exact cross multiplication, with no rounding tolerance.

Run a mixed batch:

```sh
python scripts/audit_images.py --manifest images.json --output image-quality.json
```

Or inventory a dedicated input folder with one shared target. Every non-hidden
regular file is inspected, including unsupported extensions. Store the output
and inventory outside that folder:

```sh
python scripts/audit_images.py --directory artwork --recursive --profile square_2000 --output image-quality.json --write-manifest images.json
python scripts/audit_images.py --manifest images.json --root artwork --output image-quality.json
```

Folder inventory defaults to `listing` / `user_supplied`. Edit roles, sets,
references and expectations in the saved manifest before visual review. Empty
batches are errors. List unavailable historical assets only if you have their
actual expected file names; otherwise state that they were not examined.

## Automated checks and limits

Each image receives actual dimensions, stored dimensions, EXIF orientation,
decoded format, byte count, frame count, SHA-256, check codes and specific
recommendations. Missing measurements remain null. Files over 50 MiB or 40 MP
are rejected before full decoding to bound memory; do not scale a product to
bypass these limits. For over-limit files the byte count remains null because
the entire file was not read.

Checks cover complete decoding, true format, matching extension, a single
frame, target size, ratio, optional minimum resolution and byte limit. Formats
decoded are PNG/JPEG/WebP/GIF/BMP/TIFF; being decodable does not make a format
permitted by the target. EXIF orientation is applied before dimension checks.
The report never embeds EXIF, GPS, raw metadata, local absolute paths or images.

For `extension`, the full original must fit at 1:1 at the declared offset.
`vertical` additionally requires unchanged width and x=0. Exact decoded RGBA
equality establishes only that the original rectangular region was preserved;
it cannot establish natural lighting or seamless background generation.
Changed pixels produce `needs_review`, not an invented diagnosis of stretching:
lossy encoding, color changes and editing can all cause differences. A current,
documented `background_extension: pass` may resolve this review signal while
the automatic result remains `needs_review`. Missing references and geometric
failures cannot be waived by a human pass.

If a 2000px-wide source cannot fit a 600px-wide canvas without scaling/cropping,
state the conflict and obtain a compatible source or revised delivery target.
Never recommend shrinking or cropping the product to satisfy both constraints.
Without an original and offset, do not claim that background-only expansion
has been verified, even when the final image is 4:3.

## Visual review and approval

Use the original images at 100%, verified product/remote/dimension references,
and a side-by-side view of the whole set. The HTML gives file names and hashes;
open the source files locally for pixel inspection. Review all six items:

1. `product_appearance`: shape, color, top, grille, proportions, screen digits.
2. `accessories`: attachment structure, connector, remote buttons and quantities.
3. `text_annotations`: spelling, values, units, dimension lines and supported claims.
4. `logo`: unwanted brand names, logos, text, reflections and extraneous objects.
5. `set_consistency`: fonts, tone, composition and product details across the set.
6. `background_extension`: scaling/crop/position, seams, textures, light and new objects.

For each issue record its location, comparison source, observed discrepancy and
concrete correction. Do not report an OCR/logo/model observation as a confirmed
defect until checked against the original. This implementation performs no
automatic semantic, OCR or logo detection; all six items start `pending`.

After inspection, add a `review` to that asset in the manifest. Copy the exact
`review_fingerprint` from the latest result; do not invent a digest. Example
shape (replace the descriptive fingerprint text before running):

```json
{
  "fingerprint": "COPY_THE_64_CHARACTER_REVIEW_FINGERPRINT",
  "reviewer": "design-reviewer-1",
  "reviewed_at": "2026-10-22T17:00:00+08:00",
  "items": {
    "product_appearance": {"status": "pass", "note": "Top and grille match product reference; screen reads 95."},
    "logo": {"status": "fail", "note": "Unwanted mark remains on the remote, lower right.", "recommendation": "Remove the mark while preserving the remote's buttons and texture."}
  }
}
```

Only record decisions actually made. Omitted items remain pending. Allowed
statuses are `pass`, `fail`, `pending`, `not_applicable`; every supplied item
needs a note, and failures need a recommendation. `not_applicable` requires a
reason; product appearance and a declared extension cannot be skipped. Use a
reviewer alias rather than personal contact details. Re-run the audit afterward.

The digest binds the current file bytes, references, requirements and all
members of `set_id`. Changes invalidate the old review. Reordering the manifest
does not invalidate it. This prevents accidental stale approvals; it is not a
cryptographic signature proving the reviewer's identity or judgment.

Overall status is `blocked` for confirmed automatic/manual failures,
`needs_review` for incomplete/stale or unresolved review, and `pass` only when
all applicable gates are complete. `approved` is true only when every asset
passes. Automatic and visual statuses remain separate in JSON and HTML.

## Report integration and release gates

The existing evidence 1.0 schema is unchanged. Opt in by supplying the same
image manifest and root to rendering and validation; both recompute from files
instead of trusting a potentially stale result JSON:

```sh
python scripts/render_report.py --input input.json --evidence evidence.json --image-manifest images.json --output report.html
python scripts/validate_delivery.py --input input.json --evidence evidence.json --image-manifest images.json --report report.html --output validation.json
```

A diagnostic report may validly describe failed/pending images. Delivery
validation confirms the exact per-image section and sensitive-data scan, and
returns `images_approved` separately. Omitting the manifest for an image report
fails validation. Custom templates must include `{{IMAGE_QUALITY}}`.

Before approving the creative files themselves, use strict gates:

```sh
python scripts/audit_images.py --manifest images.json --output image-quality.json --require-approval
python scripts/validate_delivery.py --input input.json --evidence evidence.json --image-manifest images.json --report report.html --require-image-approval --output validation.json
```

Exit 0 means the diagnostic ran successfully, even if it found image problems.
With the strict flag it means every image is approved. Exit 2 means a contract,
I/O/dependency error, or a strict approval gate failed. JSON carries each issue.
Never deliver a report with `valid:false`; do not equate `valid:true` on a
diagnostic report with permission to deliver its creative assets.

## Synthetic fixtures

The repository's `tests/generate_image_fixtures.py` regenerates small synthetic
geometric drawings in `tests/fixtures/images`. `images.manifest.json` covers all
four requested resolutions, a background-only extension, a deliberate wrong
size and a custom brand-story target. No real product, customer image, account,
personal information or completed human review is represented. All visual
decisions in the example remain pending; never relabel these as actual work.
