## Inflation index

In this prompt I will lay out changes related to indexing additional revenue to inflation.

- In macro.yaml, create a new field "inflation:" and within that field, "pce:" (for pce inflation) and "cpi:" (for cpi inflation). I want to enter inflation rates in the same format as the other growth rates; that is for example "{2025: 3.1, 2026: 2.9, …}". 
- When additional-revenue is enabled, instead of specifying the dollar amount or percentage of GDP in every year, we will specify an anchor amount (to be applied to the anchor year) and specify an "index:" (put the index field inside the additional-revenue field in the yaml). The index can be "None", "PCE", or "CPI".
- If additional revenue is indexed to PCE, it will increase each year at the PCE rate for that year. Same for CPI. If index is "None", the additional revenue will stay constant every year (either in dollar terms or % GDP terms, whichever mode is enabled).

And also an output change: The config echo is currently written to output as .json. I would also like to save a .yaml copy - exactly as it exists in the input folder.