## Output Enhancements Spec (feature/output)

### Overview
Define precise, testable changes to where outputs are written, chart content/formatting, and run logging for the forward interest expense pipeline.

### Scope
- Redirect all run artifacts to a timestamped folder under `output/`.
- Add a new chart overlaying historical and forward interest expense with a visible cutoff annotation.
- Fix labels/formatting on annual charts for fiscal and calendar years.
- Add end-to-end logging that writes a single `run_forward.log` for each run.

### Out of Scope
- Changes to upstream data preparation or modeling logic beyond what is required to produce the specified outputs and annotations.
- Any reorganization of existing non-timestamped historical outputs.

## Requirements

### R1. Timestamped output directory
- On every run, create a unique directory: `output/{timestamp}/`.
- Timestamp format: UTC, `YYYYMMDDTHHMMSSZ` (e.g., `20250910T143015Z`).
- All artifacts for that run MUST live inside this folder, preserving current sub-structure; e.g.:
  - `output/{ts}/fiscal_year/visualizations/annual_fy.png`
  - `output/{ts}/calendar_year/visualizations/annual_cy.png`
  - `output/{ts}/visualizations/historical_vs_forward.png`
  - `output/{ts}/run_forward.log`
- If the folder already exists (rare), append `-1`, `-2`, … until unique.

### R2. New chart: Historical vs Forward Interest Expense
- Create a chart overlaying historical and forward interest expense on the same axes.
- Visually annotate the cutoff between historical and future with a vertical line and label (e.g., "forecast starts").
- Ensure both series share units and are clearly distinguishable (color/linestyle/legend entries).
- Save to: `output/{timestamp}/visualizations/historical_vs_forward.png`.

### R3. Annual charts axis/label fixes
- On fiscal year annual chart (`annual_fy.png`) and calendar year equivalent (`annual_cy.png`):
  - Right y-axis title MUST read: `USD trillions` (not millions).
  - The % GDP axis tick labels MUST be formatted as percentages with 1 decimal place (e.g., `0.031` -> `3.1%`).
- Save the corrected files under the timestamped output structure defined in R1.

### R4. End-to-end logging
- Create one log file per run: `output/{timestamp}/run_forward.log`.
- Default level: INFO. Include DEBUG when `--debug` flag or env var is set.
- Log the following milestones at minimum:
  - Run start/end with timestamp and code version (git SHA if available).
  - Effective configuration/provenance (paths, selected scenario, seeds).
  - Data load steps and record counts.
  - Model/forecast execution start/end and key parameters.
  - Chart generation steps with final file paths.
  - Any warnings and full stack traces for errors.
- Ensure duplicate handlers are not attached on repeated invocations within the same process.

## Implementation Notes
- Use `pathlib` and `timezone.utc` to build and create the `output/{timestamp}` directory.
- Centralize the run directory creation so all modules receive the path (pass explicitly or via context object/env var).
- Use matplotlib formatters for percentage ticks with 1 decimal (e.g., `PercentFormatter(xmax=1, decimals=1)`).
- Ensure right y-axis label text is set to `USD trillions` on both annual charts.
- For the cutoff annotation, use a vertical line (`ax.axvline`) and text label that does not overlap data.
- Keep filenames stable as specified; update any hardcoded paths in scripts (e.g., `scripts/run_forward.py`) to respect R1.

## Acceptance Criteria
- A run produces a unique `output/{timestamp}` folder in UTC format and contains all expected files.
- `historical_vs_forward.png` exists and clearly shows both series with a labeled cutoff.
- `annual_fy.png` and `annual_cy.png` in the timestamped directories have:
  - Right y-axis title exactly `USD trillions`.
  - % GDP axis ticks rendered as percentages with exactly 1 decimal place.
- `run_forward.log` exists, is non-empty, and includes the milestones listed in R4.
- All new or updated tests pass, and interest expense sanity checks pass as part of the test run, per user preference.

## Test Plan
Automated tests (pytest):
- Directory creation: Execute a dry-run or small run and assert a new `output/{timestamp}` directory is created; ensure it differs across two successive invocations.
- Logging: After a run, assert `run_forward.log` exists and contains markers like `RUN START`, `RUN END`, and at least one chart path.
- Annual charts labels:
  - Programmatically load the matplotlib figure objects in test mode (or inspect labels via saved metadata/hooks) and assert:
    - Right y-axis title text equals `USD trillions`.
    - The % GDP axis tick labels match regex `^\d+\.\d%$` (1 decimal place).
- Historical vs Forward chart:
  - Verify the file exists and that the legend contains entries for both Historical and Forward series, and that a cutoff annotation object is present on the axes.
- Sanity checks: Validate that computed effective rate and/or % GDP share remain within plausible bounds (configurable; default checks ensure values are non-negative and within realistic ranges). Failing checks should fail the test.

## Rollout & Backward Compatibility
- New timestamped directory structure is additive. If callers depend on non-timestamped paths, update them in the same change set to read from the provided run directory.
- No destructive migration of existing historical outputs is required.

## Observability & Diagnostics
- Include run directory path and git SHA (if available) at the top of `run_forward.log`.
- Optionally echo effective config to `output/{timestamp}/diagnostics/config_echo.json` if already supported by the pipeline.

## Risks & Mitigations
- Risk: Hardcoded output paths in existing code. Mitigation: Funnel all writes through a single path provider.
- Risk: Label formatting differences across matplotlib versions. Mitigation: Pin/verify formatter behavior in tests.
- Risk: Timezone inconsistencies. Mitigation: Use UTC-only timestamp generation; test on CI.


