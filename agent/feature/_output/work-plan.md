## Work Plan: Output Enhancements (feature/output)

### Goals
- Implement spec requirements R1–R4 for timestamped outputs, new chart, annual chart label fixes, and end-to-end logging.
- Ensure robust tests and sanity checks accompany each change.

### Deliverables
- Timestamped run directory for all artifacts per run.
- `historical_vs_forward.png` with cutoff annotation.
- Corrected `annual_fy.png` and `annual_cy.png` labels/formatting.
- Single `run_forward.log` per run with required milestones.
- Automated tests validating behavior.

### Traceability (Spec → Tasks)
- R1 → T1, T3, T6
- R2 → T4, T7
- R3 → T5, T7
- R4 → T2, T6, T7

## Sequenced Tasks

### T1. Introduce run directory provider (R1)
- Create a small utility to generate a UTC timestamp `YYYYMMDDTHHMMSSZ` and create `output/{timestamp}`.
- Expose a single function returning the run directory `Path` and ensuring subdirs are created lazily.
- Integrate at the start of `scripts/run_forward.py` and pass the run directory downstream (context object or explicit parameter).

### T2. Initialize logging (R4)
- Add a logging setup that writes to `{run_dir}/run_forward.log` at INFO by default; DEBUG when `--debug` (new CLI flag) or env var is set.
- Include run start/end, git SHA (if available), configuration echo path, and key milestones.
- Guard against duplicate handlers in repeated invocations (idempotent setup).

### T3. Route all outputs through the run directory (R1)
- Replace hardcoded `output/...` paths by deriving from `run_dir` for:
  - Config echo, previews, diagnostics, UAT, annual CSVs, visualizations, perf profile.
- Centralize path joins in an `OutputPaths` helper to reduce churn and errors.

### T4. Add Historical vs Forward chart (R2)
- Construct annual series by combining historical diagnostics with annualized forward monthly trace:
  - Historical: use `diagnostics/interest_fy_totals.csv` and `diagnostics/interest_cy_totals.csv` up to the anchor date.
  - Forward: aggregate the monthly trace table to FY and CY totals. If the anchor date falls mid-year, form the anchor-year total as (historical months YTD) + (forward months remaining) for that same year.
- Overlay historical vs forward on a single chart with shared units/styles; include a legend that distinguishes historical and forward segments.
- Add a vertical cutoff annotation at the anchor date (last historical month) with a label.
- Save to `{run_dir}/visualizations/historical_vs_forward.png` and log the path.

### T5. Fix annual chart labels/formatting (R3)
- In the annual FY and CY chart generation code:
  - Set right y-axis title to `USD trillions`.
  - Format % GDP axis ticks with 1 decimal using a matplotlib percent formatter with `xmax=1`.
- Ensure both `annual_fy.png` and `annual_cy.png` are saved under the timestamped structure.

### T6. CLI enhancements and plumbing (R1, R4)
- Add `--debug` flag to `scripts/run_forward.py` to elevate logging level.
- Optionally accept `--outdir` to override timestamped dir (for reproducible tests); default remains timestamped.
- Echo effective configuration and run directory at startup in logs and stdout.

### T7. Tests and sanity checks (all)
- Add pytest cases:
  - Directory creation uniqueness across two runs; structure contains expected subpaths.
  - Logging file exists, non-empty, includes `RUN START`/`RUN END`, and chart file paths.
  - Annual charts: verify right y-axis label text and percent tick formatting (1 decimal) via figure objects or saved metadata prior to save.
  - Historical vs Forward: file exists; legend includes both series; cutoff annotation present.
  - Sanity checks for interest expense metrics (non-negative, within plausible bounds); failing bounds should fail tests.

## Implementation Outline
- Create `OutputPaths` and logging setup utilities (e.g., under `src/`), import and use in `scripts/run_forward.py`.
- Touch minimal call sites to route writes via `OutputPaths`.
- For plotting, ensure headless backend is used when diagnostics flag is set; keep filenames stable.
- Use `pathlib` everywhere; avoid string path concatenation.

## Acceptance Criteria (summary)
- Single timestamped run folder contains all artifacts.
- `historical_vs_forward.png` shows both series with a labeled cutoff.
- Annual charts have right y-axis title `USD trillions` and % GDP ticks as percentages with 1 decimal.
- `run_forward.log` exists with required milestones.
- All new tests pass and sanity checks succeed.

## Risks & Mitigations
- Hardcoded paths missed: funnel writes via `OutputPaths` and grep for `output/` usages.
- Matplotlib version differences: pin formatter behavior in tests.
- Timezone formatting inconsistencies: enforce UTC-only timestamp generation and test.

## Rollout Plan
- Land utilities and plumbing (T1–T3) behind non-breaking defaults.
- Add charts/label fixes (T4–T5).
- Introduce CLI flags and logging (T2, T6).
- Add tests (T7) and ensure CI passes.

## Definition of Done
- All tasks T1–T7 completed.
- Tests added and passing; interest expense sanity checks pass.
- Spec acceptance criteria are met; artifacts observed in a local run.


