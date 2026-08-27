# Contributing

Contributions are welcome when they preserve evidence integrity, privacy, and
repeatability.

## Before opening a pull request

1. Create a focused branch.
2. Add or update tests before changing a contract.
3. Use synthetic ASINs such as `B000000001`; never use customer data as a
   fixture.
4. Run the complete test suite and the official Skill validator.
5. Render and validate the synthetic end-to-end report.
6. Review the staged diff and commit history for private material.

## Required checks

```powershell
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
python .github/scripts/validate_skill.py skills/amazon-parent-asin-audit
python skills/amazon-parent-asin-audit/scripts/render_report.py `
  --input tests/fixtures/input.valid.json `
  --evidence tests/fixtures/evidence.conflicting.json `
  --output tmp/report.html
python skills/amazon-parent-asin-audit/scripts/validate_delivery.py `
  --input tests/fixtures/input.valid.json `
  --evidence tests/fixtures/evidence.conflicting.json `
  --report tmp/report.html
```

Metadata validation uses the pinned PyYAML development dependency. Project
runtime scripts intentionally use only the Python standard library.

## Privacy rules

Do not commit:

- Tokens, API keys, Authorization headers, cookies, JWTs, or private keys.
- Seller account identifiers, personal emails, or raw seller exports.
- Customer ASINs, reports, screenshots, or personal publishing domains/project
  identifiers.
- Connector responses containing fields unrelated to a sanitized test.

Fixtures must be synthetic and must state that they are synthetic.

## Contract changes

Schema or evidence-class changes require:

- A failing test demonstrating the new behavior.
- Matching updates to `references/evidence-contract.md`.
- Backward-compatibility notes or an explicit schema-version change.
- A rendered fixture proving the report still passes delivery validation.

## Pull request scope

Keep changes focused. Explain the evidence failure mode being addressed and how
the test prevents regression. Do not combine unrelated report redesigns,
connector additions, and schema changes in one pull request.
