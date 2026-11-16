# International Cost of Capital

A Streamlit app that compares a project's cost of equity, cost of debt and WACC
in U.S. dollars and in the currency of any selected country.

## Run

```bash
pip install -r requirements.txt
```

```bash
streamlit run app.py
```

The app opens with Software (System & Application), the United States as the
target country, the U.S. tax rate, a 6.5% equity risk premium and 30% debt.

## Data

| Input | Source |
| --- | --- |
| Industry unlevered betas | [Damodaran – betas.xls](https://pages.stern.nyu.edu/~adamodar/pc/datasets/betas.xls) |
| USD BBB spread (Baa2/BBB, large non-financial service firms) | [Damodaran – ratings](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/ratings.html) |
| Corporate tax rates (combined statutory) | OECD Corporate Tax Statistics, via the OECD data API (`DSD_TAX_CIT@DF_CIT`) |
| 10-year government bond yields | OECD Main Economic Indicators, via the OECD data API (`DSD_STES@DF_FINMARK`) |

Data is fetched live, cached for 24 hours, and re-downloaded with the
**Refresh data** button. The *Data sources* tab shows each source, the date of
the data and when it was fetched. If a source cannot be reached, the app falls
back to `data/snapshot.json` and says so; rebuild the snapshot with
`python data_sources.py`.

The OECD report page for statutory tax rates is protected by a browser check
and cannot be read by a script, so the same dataset is read from the OECD data
API, which also carries more recent years.

## Method

- Re-levered beta: βL = βU × [1 + (1 − t) × D/E]
- Cost of equity = government bond yield of the currency + βL × equity risk premium
- Cost of debt = government bond yield of the currency + BBB spread
- Foreign BBB spread (auto) = USD spread × (1 + foreign yield) / (1 + U.S. yield)
- WACC = E/V × cost of equity + D/V × cost of debt × (1 − t)

The same project tax rate (U.S. or selected country), debt share and equity
risk premium are used in both currencies. Every fetched input can be replaced
by a manual value in the sidebar.

## Files

- `app.py` – Streamlit UI
- `finance.py` – cost of capital formulas
- `data_sources.py` – data fetching and snapshot fallback
