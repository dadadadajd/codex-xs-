# Amazon Parent ASIN Audit Skill

[中文说明](README.zh-CN.md)

A reusable Codex Skill for evidence-backed Amazon parent/child ASIN market,
keyword, advertising-boundary, and listing audits. It produces structured JSON,
a portable single-file HTML report, and a machine-readable release validation.

The workflow works with live Amazon evidence alone and becomes deeper when SIF,
Sorftime, or covered seller-backend connectors are available. Missing sources
degrade explicitly instead of becoming fake zeros or stale replacements.

## Why this exists

Amazon family audits fail in predictable ways:

- A provider repeats a parent-family sales series for every child and the values
  are accidentally summed.
- One child inherits a sibling's stronger specification.
- Traffic scores or sponsored visibility are presented as spend, CPC, or ACOS.
- Different keyword providers are averaged into one false "confirmed" number.
- An unavailable connector is silently replaced with an older result.
- A shareable report leaks credentials, customer data, or publishing IDs.

This Skill turns those failure modes into explicit contracts and automated
quality gates.

## Capabilities

- Parent/child scope reconciliation and child-specific action matrices.
- Live Amazon evidence with capture timestamps.
- Optional SIF and Sorftime keyword, category, competitor, and demand evidence.
- Strict front-end versus Amazon Ads backend metric boundaries.
- Duplicate family-series detection without child double-counting.
- Side-by-side cross-source keyword estimates.
- Responsive, print-friendly, offline HTML rendering.
- Delivery checks for ASIN/source coverage, unresolved placeholders, and common
  sensitive-data patterns.
- Optional batch image checks for dimensions, ratios, encoding and delivery
  targets, with separate recorded visual reviews and per-file HTML findings.
- Optional public publishing workflow after explicit user authorization.

## Repository layout

```text
skills/amazon-parent-asin-audit/
├── SKILL.md
├── agents/openai.yaml
├── assets/report-template.html
├── references/
│   ├── evidence-contract.md
│   ├── quality-gates.md
│   ├── report-contract.md
│   └── source-adapters.md
└── scripts/
    ├── common.py
    ├── render_report.py
    ├── validate_delivery.py
    ├── validate_evidence.py
    └── validate_input.py
```

## Installation

Clone this repository, then copy `skills/amazon-parent-asin-audit` into your
Codex skills directory using the same folder name. Restart or refresh Codex so
the Skill catalog is reloaded.

You can also run the scripts directly. They require Python 3.10 or later. The
original workflow uses only the standard library; image audits additionally
need `pip install -r skills/amazon-parent-asin-audit/requirements-images.txt`.

## Image and A+ quality checks

See [the image-quality contract](skills/amazon-parent-asin-audit/references/image-quality.md)
for mixed-size manifests, folder batches, full commands and visual review records.
Presets cover 2000×2000, 1600×1600, 1464×600, 600×450 and ratio-only 4:3;
custom sizes support brand-story and other placements.

```sh
python skills/amazon-parent-asin-audit/scripts/audit_images.py --manifest tests/fixtures/images.manifest.json --output tmp/image-quality.json
python skills/amazon-parent-asin-audit/scripts/render_report.py --input tests/fixtures/input.valid.json --evidence tests/fixtures/evidence.conflicting.json --image-manifest tests/fixtures/images.manifest.json --output tmp/images-report.html
python skills/amazon-parent-asin-audit/scripts/validate_delivery.py --input tests/fixtures/input.valid.json --evidence tests/fixtures/evidence.conflicting.json --image-manifest tests/fixtures/images.manifest.json --report tmp/images-report.html
```

The report lists actual properties and specific corrections per file, plus
manual checks of appearance, accessories, text, logos, set consistency and
background expansion. With an original and offset, the module can check that
the original pixel region was preserved; the ratio alone cannot prove this.
It does not perform automatic OCR, semantic comparison or logo detection.

The included drawings are entirely synthetic, with one deliberate size failure
and no claimed human approval. A valid diagnostic report does **not** approve
the images. Add `--require-image-approval` to delivery validation (or
`--require-approval` to the image CLI) for final creative approval. Existing
commands without image arguments remain compatible and make no image claims.

## Use in Codex

Example request:

```text
Use amazon-parent-asin-audit to analyze parent ASIN B000000000 and children
B000000001, B000000002 on Amazon US. Use live Amazon plus SIF and Sorftime when
available. Produce a Chinese offline HTML report, keep all source estimates
separate, and do not publish it.
```

For a public report, explicitly name the destination or ask for a public,
shareable link. Publishing is never assumed from an ordinary audit request.

## Run the synthetic example

From the repository root:

```powershell
python skills/amazon-parent-asin-audit/scripts/validate_input.py `
  --input tests/fixtures/input.valid.json

python skills/amazon-parent-asin-audit/scripts/validate_evidence.py `
  --evidence tests/fixtures/evidence.conflicting.json

python skills/amazon-parent-asin-audit/scripts/render_report.py `
  --input tests/fixtures/input.valid.json `
  --evidence tests/fixtures/evidence.conflicting.json `
  --output tmp/report.html

python skills/amazon-parent-asin-audit/scripts/validate_delivery.py `
  --input tests/fixtures/input.valid.json `
  --evidence tests/fixtures/evidence.conflicting.json `
  --report tmp/report.html
```

The fixtures are synthetic and contain no customer ASINs or account data.

## Output contract

```text
outputs/<parent>-<marketplace>-<date>/
├── input.json
├── evidence.json
├── report.json          # optional structured narrative
├── report.html
└── validation.json
```

Do not deliver or publish when `validation.json` has `"valid": false`.

## Connector behavior

Connectors are discovered by capability rather than fixed MCP tool names. The
Skill remains useful when optional connectors are missing:

| Source | Without it |
|---|---|
| Live Amazon | Stop current-price/listing claims or use a clearly labelled current user export |
| SIF | Mark SIF estimates unavailable; do not copy an older run |
| Sorftime | Mark category/modelled demand unavailable; do not copy an older run |
| Amazon Ads backend | Keep spend, CPC, orders, ACOS, ROAS, and budgets unavailable |
| Public host | Deliver the validated local HTML only |

## Tests

```powershell
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
python .github/scripts/validate_skill.py skills/amazon-parent-asin-audit
```

To additionally run an installed Codex distribution's official validator after
installing the development requirement:

```powershell
python path/to/skill-creator/scripts/quick_validate.py `
  skills/amazon-parent-asin-audit
```

GitHub Actions runs the test suite, Skill validation, synthetic render, and
delivery validation on Python 3.10 and 3.12.

## Privacy and safety

- Never commit connector tokens, cookies, JWTs, seller reports, customer
  fixtures, or personal publishing identifiers.
- Treat third-party demand and sales values as estimates.
- Respect marketplace authentication, CAPTCHA, quotas, and access controls.
- Keep external publishing behind explicit user authorization.

See [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request.

## License

[MIT](LICENSE)
