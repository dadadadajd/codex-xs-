# Evidence Contract

Image checks use a separate optional `images.json` manifest and generated
`image-quality.json`; see [image-quality.md](image-quality.md). Evidence schema
1.0 and existing required fields are unchanged. Use `--image-manifest` on the
renderer and delivery validator to add recomputed image findings. Do not insert
unsupported image fields into evidence or treat pending visual reviews as facts.

Use this contract when creating or reviewing `evidence.json`. The report may be
written in any supported language, but field names stay in English.

## Top-level object

```json
{
  "schema_version": "1.0",
  "captured_at": "2026-08-27T06:00:00Z",
  "sources": [],
  "parent": {},
  "children": [],
  "market": {},
  "keywords": [],
  "competitors": [],
  "advertising": {},
  "listing": {},
  "summary": [],
  "actions_30_60_90": {"30": [], "60": [], "90": []},
  "limitations": []
}
```

The validator accepts only these top-level fields. Put seller/account IDs,
credentials, connector responses, and unrelated metadata outside the delivery
bundle; unknown top-level fields fail closed.

Available numeric metrics must contain a finite number, a unit, and non-empty
notes. Their `source` and `source_type` must match a record in `sources`; an
available metric cannot cite a source whose registry status is unavailable.

Use ISO-8601 timestamps. `captured_at` describes the run; individual metrics
keep their own capture timestamps when they differ.

## Source records

Each source record contains:

```json
{
  "source": "amazon-us-live",
  "source_type": "amazon_live",
  "status": "available",
  "captured_at": "2026-08-27T06:00:00Z",
  "notes": "US delivery location verified; price is time-sensitive."
}
```

Allowed `source_type` values:

- `amazon_live`
- `seller_backend`
- `sif`
- `sorftime`
- `user_document`
- `analyst`

Allowed `status` values are `available`, `partial`, and `unavailable`.
Unavailable sources use `captured_at: null` and explain the failure in `notes`.

## Metric records

Every material numeric value uses:

```json
{
  "name": "median_price",
  "value": 219.99,
  "unit": "USD",
  "source": "sorftime",
  "source_type": "sorftime",
  "evidence_class": "third_party_estimate",
  "scope": "category",
  "captured_at": "2026-08-27T06:02:00Z",
  "status": "available",
  "notes": "Top-100 modelled category estimate."
}
```

Allowed `evidence_class` values:

- `confirmed_live`: visible on the marketplace at capture time.
- `backend_confirmed`: established by a covered seller/backend report.
- `third_party_estimate`: modelled by SIF, Sorftime, or another named provider.
- `historical_detection`: captured earlier or in a historical source.
- `inference`: analyst reasoning derived from labelled evidence.
- `unavailable`: not established in this run.

Allowed `scope` values:

- `parent_family`
- `child_asin`
- `keyword`
- `competitor`
- `category`
- `campaign`

An unavailable metric must use `value: null`, `status: "unavailable"`,
`evidence_class: "unavailable"`, and a non-empty `reason`. Never use `0` to
mean unavailable.

## Claim records

Material narrative conclusions and recommendations are structured claims, not
bare strings:

```json
{
  "text": "Verify this child's specifications before copy changes.",
  "source": "analyst-review",
  "source_type": "analyst",
  "evidence_class": "inference",
  "scope": "child_asin",
  "captured_at": "2026-08-27T06:05:00Z",
  "status": "available",
  "notes": "Bounded recommendation derived from labelled child evidence."
}
```

Use claim records for parent title, category, summaries, child findings/actions,
competitor similarity, front-end advertising observations, listing findings,
and 30/60/90-day actions. Each claim source must exist in the source registry.
Limitations may remain plain strings because they describe absence or scope
rather than assert a material product or performance fact.

## Children

Each child appears once:

```json
{
  "asin": "B000000001",
  "label": "Standard",
  "price": {"value": 199.99, "unit": "USD", "scope": "child_asin"},
  "sales_series": {
    "points": [
      {"period": "2026-07", "value": 15},
      {"period": "2026-08", "value": 20}
    ],
    "unit": "units/month",
    "source": "sorftime",
    "source_type": "sorftime",
    "evidence_class": "third_party_estimate",
    "scope": "parent_family",
    "captured_at": "2026-08-27T06:02:00Z",
    "status": "available",
    "notes": "Child lookup returned a likely family-level series."
  },
  "findings": [
    {
      "text": "Child-specific fact",
      "source": "analyst-review",
      "source_type": "analyst",
      "evidence_class": "inference",
      "scope": "child_asin",
      "captured_at": "2026-08-27T06:05:00Z",
      "status": "available",
      "notes": "Bounded interpretation of labelled child evidence."
    }
  ],
  "actions": [
    {
      "text": "Child-specific action",
      "source": "analyst-review",
      "source_type": "analyst",
      "evidence_class": "inference",
      "scope": "child_asin",
      "captured_at": "2026-08-27T06:05:00Z",
      "status": "available",
      "notes": "Bounded recommendation for this child only."
    }
  ]
}
```

The abbreviated price above still needs all metric provenance fields in the
actual file. Price is mandatory: if it cannot be observed, provide an explicit
unavailable metric with `value: null`, provenance, and a reason. `sales_series`
always carries provider, unit, scope, status, capture time, and notes. Do not
copy sibling facts into this object.

## Family-series deduplication

Third-party child lookups sometimes repeat a parent-family sales series. The
validator fingerprints period/value pairs independent of their input order.
When two or more children have an identical non-empty fingerprint:

1. Retain the raw child responses for traceability.
2. Emit `DUPLICATE_CHILD_SERIES`.
3. Treat the unique series as one likely `parent_family` estimate.
4. Display the complete deduplicated period/value series once.
5. Never sum the duplicated series.
6. Do not allocate it back to children without child-level evidence.

If series differ, keep them separate. Do not assume they are child-level unless
the provider's field definition confirms that scope.

## Cross-source differences

Keep each estimate in the keyword's `estimates` array. Preserve source, period,
unit, and notes. Do not average estimates into a verified number. Explain likely
differences in window, geography, keyword normalization, or methodology only as
inference.

## Backend coverage

Seller backend metrics must say which dates, campaigns, ad products, stores,
and ASINs the source covers. Never allocate a partial report to uncovered
children or treat a product-ad report as account-wide.
