# Sources for the 60-second voice sample

| Claim | Basis |
|---|---|
| $5,000 at 24% APR, minimum payments: nearly 20 years (19.5), about $8,900 interest ($8,887) | Calculation: `glivarao.content.calculators.minimum_payment_payoff(5000, 0.24)`; minimum = 1% of balance + interest, at least $25 (a common issuer formula; "typical", not universal) |
| $200/month: about 3 years (36 months), roughly $2,000 interest ($2,001) | Calculation: `fixed_payment_payoff(5000, 0.24, 200)` |
| More than 8,000 complaints (8,107) about purchases on statements (CFPB issue "Problem with a purchase shown on your statement"), 2026-08-19 to 2026-11-17, up 58% vs 5,131 a year earlier | CFPB Consumer Complaint Database (CC0), retrieved 2026-11-18. Complaints are not a statistical sample. |
