# Report Contract

The report must help an operator decide what is known, what is estimated, what
to do next, and what evidence is still missing.

## Required sections

### Executive summary

State the parent, marketplace, child coverage, source coverage, three to five
material findings, and the most important evidence limitation. Lead with
decisions, not collection chronology.

### Source status

List every planned source as available, partial, or unavailable with capture
time and scope. A failed source is a report result, not a reason to hide the
section.

### Parent and child matrix

Use one row per requested child. Include variation label, currently visible
price/coupon when available, verified distinguishing facts, listing/review
signals, child-specific action, and claim-level price provenance. List
discovered out-of-scope children in a note rather than inserting them silently.

### Market evidence

Describe the exact category/node or search context. Show size, price, review,
brand concentration, return, or sales estimates only when sourced. Separate
product segments when price or use case is not like-for-like.

### Keyword comparison

Show phrase, source, window, estimate, unit, and CPC only when the source
provides it. Retain cross-source differences. Use demand/rank evidence to shape
listing and test priorities, not to fabricate backend performance.

Every table containing a material metric must show claim-level provenance:
source, evidence class, capture time, scope, and status. A global source-status
table does not replace this linkage.

Material narrative findings and actions use the same provenance fields and are
linked in the HTML through a unique evidence path. Bare free-text claims are a
contract error.

### Competitor context

Select competitors by product type, core specification, use case, and price
segment. Explain mismatches. A popular but mechanically different product is a
market reference, not a direct listing benchmark.

### Advertising boundaries

Split the section into:

- Front-end observations: sponsored visibility, rank, traffic/index signals.
- Backend-confirmed metrics: spend, clicks, CPC, orders, sales, ACOS, ROAS,
  placements, budgets, and search terms within documented coverage.
- Missing backend inputs: exact report needed to make the next decision.

Do not recommend a numeric bid or budget from front-end-only evidence. A formula
or test range may be shown only when its inputs and assumptions are explicit.

### Listing findings

Check parent/child consistency, title and bullets, verified specifications,
images, video, A+, brand story, price/coupon presentation, reviews, and visible
contradictions. Tie each rewrite or creative action to an evidence-backed gap.

### Child-specific actions

Each requested child gets a separately reviewable action. Never apply one
child's stronger specification or customer proof to the family.

### 30/60/90-day plan

- 30 days: repair evidence, listing integrity, urgent availability/review risk,
  and collect missing backend reports.
- 60 days: run bounded creative, keyword, price/promotion, or campaign tests.
- 90 days: re-pull live evidence, evaluate like-for-like windows, and scale only
  validated winners.

### Limitations and evidence appendix

Explain connector failures, stale or historical facts, third-party estimates,
coverage limits, marketplace location, capture time, and decisions that remain
unavailable.

## Writing rules

- Use precise units and windows.
- Say `unavailable`, not `zero`, when data is missing.
- Say `estimate`, not `sales`, for modelled values.
- Say `observed`, not `confirmed backend performance`, for front-end signals.
- Identify inference explicitly.
- Keep source disagreements visible.
- Avoid generic PPC or listing advice that cannot be traced to evidence.

## Output files

```text
outputs/<parent>-<marketplace>-<date>/
├── input.json
├── evidence.json
├── report.json          # optional structured narrative/findings
├── report.html
└── validation.json
```

`report.html` must be self-contained unless the chosen host explicitly requires
external assets. The default template uses no client-side JavaScript or remote
fonts.
