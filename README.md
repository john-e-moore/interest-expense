# Interest Expense

Forward interest expense engine.

Configuration snippet: Additional revenue offset

Add an optional block under `deficits` to reduce the primary deficit before propagation.

Percent of GDP (FY or CY frame):
```yaml
deficits:
  frame: FY
  annual_pct_gdp:
    2026: 3.0
  additional_revenue:
    enabled: true
    mode: pct_gdp
    annual_pct_gdp:
      2026: 1.0  # 1% of GDP
```

Absolute level (USD millions per year):
```yaml
deficits:
  frame: FY
  annual_pct_gdp:
    2026: 3.0
  additional_revenue:
    enabled: true
    mode: level
    annual_level_usd_millions:
      2026: 300000  # $300 billion
```

Notes
- `enabled` defaults to false; set to true to activate.
- Positive values reduce the primary deficit (i.e., revenue increases). Negative values increase the deficit.
- Annual CSVs include an `additional_revenue` column alongside `interest`, `gdp`, and `pct_gdp` when the feature is enabled.
