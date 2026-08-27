# Amazon Parent ASIN Audit Skill Design

## Status

Approved for implementation on 2026-08-27. The target is the public repository
`dadadadajd/codex-xs-`.

## Purpose

`amazon-parent-asin-audit` turns a marketplace, one parent ASIN, and an optional
set of child ASINs into an evidence-backed market, traffic, advertising, and
listing audit. It preserves source boundaries, produces a portable HTML report,
and can optionally publish the report when the user explicitly authorizes an
external write.

The skill is intentionally product-category independent. The wheelchair report
that motivated it is an implementation reference, not a bundled fixture or a
source of reusable facts.

## Goals

- Work with only live Amazon evidence, while improving depth when SIF and
  Sorftime connectors are available.
- Reconcile parent and child variation facts without copying one child’s claims
  to another child.
- Keep observed facts, third-party estimates, historical facts, inferences, and
  unavailable backend facts visibly distinct.
- Generate a single-file HTML report that opens offline and can be shared.
- Emit structured evidence and findings so another renderer can reuse the work.
- Fail transparently when a source is unavailable; never silently substitute a
  stale result or turn missing data into zero.
- Be safe to publish: no credentials, personal domains, private seller data, or
  customer-specific fixtures in the repository.

## Non-goals

- Circumventing CAPTCHA, authentication, marketplace access controls, or MCP
  quotas.
- Claiming Amazon Ads spend, orders, ACOS, ROAS, or budgets from front-end
  observations.
- Automating irreversible campaign, listing, pricing, or account changes.
- Providing a universal sales forecast from third-party estimates.
- Hosting a report without explicit user authorization.

## Public Interface

The minimum user input is:

```json
{
  "schema_version": "1.0",
  "marketplace": "US",
  "parent_asin": "B000000000",
  "child_asins": ["B000000001"],
  "language": "zh-CN",
  "report_date": "2026-08-27",
  "publish": false
}
```

`child_asins` may be empty. The workflow then discovers variations from the live
listing or marks variation discovery unavailable. `publish` defaults to false.
Credentials and connector tokens are never accepted in this file.

## Evidence Contract

Every material metric or claim carries:

- `source`: stable connector or document label.
- `source_type`: `amazon_live`, `seller_backend`, `sif`, `sorftime`,
  `user_document`, or `analyst`.
- `evidence_class`: `confirmed_live`, `backend_confirmed`,
  `third_party_estimate`, `historical_detection`, `inference`, or `unavailable`.
- `scope`: `parent_family`, `child_asin`, `keyword`, `competitor`, `category`, or
  `campaign`.
- `captured_at`: ISO-8601 timestamp, or `null` for unavailable evidence.
- `status`: `available`, `partial`, or `unavailable`.
- `notes`: limitations needed to interpret the value.

Unavailable evidence has a `null` value and a reason. A numeric zero is valid
only when the source positively reports zero.

## Source Precedence and Reconciliation

1. User-supplied mechanical specifications override inferred or scraped product
   specifications and are labelled `user_document`.
2. Seller backend reports establish backend advertising and business metrics
   within their documented coverage.
3. Live Amazon establishes currently visible listing content, price, coupon,
   availability, rating, review count, and variation relationships.
4. SIF and Sorftime enrich keyword, category, competitor, and estimated demand
   analysis. Their estimates remain estimates even when both sources agree.
5. Analytical inference may connect evidence but cannot upgrade its evidence
   class.

Conflicting sources are shown side by side. The workflow explains likely scope,
window, or methodology differences instead of forcing a single number.

## Critical Guardrails

### Parent-family duplication

If multiple child calls return an identical sales series, the series is treated
as a likely parent-family estimate. It is displayed once and never summed across
children. The validator emits `DUPLICATE_CHILD_SERIES`.

### Child isolation

Every child keeps its own facts and recommendations. A motor rating, material,
capacity, price, coupon, or review fact may not be inherited from a sibling
without evidence that explicitly applies to the family.

### Front-end versus backend advertising

Traffic indices, visible sponsored placements, keyword ranks, and modelled
orders cannot establish spend, CPC, ACOS, ROAS, budget, or campaign settings.
Backend-required metrics are marked unavailable until a covered backend export
is supplied.

### Freshness

Each run uses captured timestamps. An unavailable current pull is not replaced
with a prior run unless the user explicitly asks for a historical comparison;
historical values remain labelled historical.

### Credentials and privacy

Tokens, cookies, JWTs, Authorization headers, account identifiers, personal
domains, and raw seller exports are excluded from logs, fixtures, reports, and
Git history. Secret scanning is a release gate.

## Workflow

1. Validate and normalize the input contract.
2. Discover available connectors and declare a source plan.
3. Collect live parent and child facts with timestamps.
4. Collect optional SIF and Sorftime evidence; record explicit source failures.
5. Reconcile parent/child coverage and detect duplicated family-level series.
6. Analyze market structure, demand, competitors, traffic/advertising evidence,
   listing quality, and child-specific actions.
7. Produce `evidence.json`, `report.json`, and a single-file HTML report.
8. Validate coverage, provenance, HTML structure, placeholders, and secrets.
9. Publish only after explicit authorization, then verify anonymous HTTP access.

## Output Contract

Each run creates:

```text
outputs/<parent>-<marketplace>-<date>/
├── input.json
├── evidence.json
├── report.json
├── report.html
└── validation.json
```

The HTML report contains:

- Executive summary and source status.
- Parent/child variation matrix.
- Category and demand evidence.
- Cross-source keyword comparison.
- Competitor segmentation and price context.
- Advertising observations with backend boundaries.
- Listing and A+ findings.
- Child-specific actions.
- 30/60/90-day execution plan.
- Limitations and evidence appendix.

## Repository Shape

```text
codex-xs-/
├── README.md
├── LICENSE
├── CONTRIBUTING.md
├── docs/superpowers/specs/
├── skills/amazon-parent-asin-audit/
│   ├── SKILL.md
│   ├── agents/openai.yaml
│   ├── assets/report-template.html
│   ├── references/
│   └── scripts/
└── tests/
    ├── fixtures/
    └── test_*.py
```

Python scripts use only the standard library. This keeps validation and
rendering available in constrained Codex environments and ordinary local
installations.

## Acceptance Criteria

- Codex skill metadata passes `quick_validate.py`.
- Unit tests pass with Python 3.10 or later and no third-party packages.
- A synthetic conflicting-source fixture renders a valid offline HTML report.
- Duplicated child sales series are detected and are not summed.
- Unavailable metrics remain `null`, with an explicit reason.
- Every child in the input appears exactly once in the child action matrix.
- The repository contains no known tokens, customer ASINs, personal domains, or
  unresolved template placeholders.
- The public GitHub URL is readable without authentication after push.
