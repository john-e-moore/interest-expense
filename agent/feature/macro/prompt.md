## Branch: feature/macro

Below is an outline of changes to implement in this branch.

- Introduce GDP growth rate to macro.yaml and use it in the model. Currently, output shows that GDP is staying flat. I want the user to be able to specify growth rate for each year. For instance, under "gdp:" in the macro.yaml file, we would have "annual_fy_growth_rate: {2025: 4.0, 2026: 3.6, 2027: 3.2, ...}" and so on.
- Compute historical monthly effective rate 
    - Melt outstanding_by_bucket_scaled to get one row per date per security bucket
    - Inner join the resulting table to interest_monthly_by_category  on month and year
    - Divide interest expense from outstanding amount to come up with effective rate
    - Write this table to .csv in the diagnostics folder for the run.
- Plot annual (for both fiscal year and calendar year) average effective rate (historical)
- Combine historical and forward effective rate data and plot them on a single chart, annotating where the forward projection starts. 
- Introduce variable rate inputs (annual) for each of SHORT, NB, TIPS in macro.yaml
