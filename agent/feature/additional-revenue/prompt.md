## Additional Revenue

I want to add a section to macro.yaml under "deficits" where I can add additional revenue either as a % of GDP or a dollar amount (millions of dollars). e.g. {2025: 1.0, 2026: 1.1, ...} (% of GDP) or {2025: 300000, 2026: 300000} (millions of dollars). This additional revenue is to be subtracted from the primary deficit each year before that gets propagated into the model. 

The primary deficit affects how much debt (shares) get issued in a given year, which affects the interest payment for that year and following years. With positive additional revenue, the primary deficit will be lowered.

Write a spec for this feature.