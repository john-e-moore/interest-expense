## Branch: feature/output

Below I will outline changes we need to make to the model's outputs.

- Each time the model is run, write all output to 'output/{timestamp}/'
- New chart: plot historical interest expense on the same chart as forward interest expense. Annotate where the historical/future cutoff is on the line chart.
- On the 'annual_fy.png' chart (and probably the calendar year equivalent) the right y-axis title should say 'USD trillions' (not millions). On the same chart, the numbers on the % GDP axis should be expressed as percentage with 1 decimal. For example, 0.031 -> 3.1%
- Add end-to-end logging and write a single run_forward.log file to the 'output/{timestamp}/' folder.