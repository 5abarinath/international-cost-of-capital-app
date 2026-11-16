"""International Cost of Capital – Streamlit app.

Compares a project's cost of equity, cost of debt and WACC in USD and in the
currency of a selected country.
"""

from __future__ import annotations

import altair as alt
import pandas as pd
import pycountry
import streamlit as st

import data_sources as ds
from finance import auto_foreign_spread, cost_of_capital

US = ds.US
DEFAULT_INDUSTRY = "Software (System & Application)"
DEFAULT_ERP = 6.5
DEFAULT_DEBT_SHARE = 30

st.set_page_config(page_title="International Cost of Capital", page_icon="🌍", layout="wide")


@st.cache_data(ttl=24 * 3600, show_spinner="Fetching latest data…")
def get_data() -> dict:
    return ds.load_all()


def flag(iso3: str | None) -> str:
    """Flag image (HTML) for an ISO 3166 alpha-3 code; globe if the code is unknown.

    An image is used instead of a flag emoji because Windows does not render
    flag emoji. The browser loads it from flagcdn.com.
    """
    match = pycountry.countries.get(alpha_3=iso3) if iso3 else None
    if not match:
        return "🌐"
    code = match.alpha_2.lower()
    return (
        f'<img src="https://flagcdn.com/w40/{code}.png" '
        f'srcset="https://flagcdn.com/w80/{code}.png 2x" alt="{match.alpha_2} flag" '
        'style="height:0.8em; vertical-align:baseline; border:1px solid rgba(128,128,128,0.4); '
        'border-radius:2px;">'
    )


def pct(x: float, digits: int = 2) -> str:
    return f"{x * 100:.{digits}f}%"


data = get_data()
betas = pd.DataFrame(data["betas"]["industries"]).set_index("industry")
tax_rates = data["tax_rates"]["rates"]
yields = data["bond_yields"]["yields"]
usd_bbb_fetched = data["bbb_spread"]["spread"]

industries = list(betas.index)
countries = [US] + sorted(c for c in tax_rates if c != US)

# --------------------------------------------------------------------------
# Sidebar – inputs
# --------------------------------------------------------------------------
with st.sidebar:
    st.header("Project")
    industry = st.selectbox(
        "Industry",
        industries,
        index=industries.index(DEFAULT_INDUSTRY) if DEFAULT_INDUSTRY in industries else 0,
    )
    country = st.selectbox(
        "Target country",
        countries,
        index=0,
        help="Countries with an OECD statutory corporate tax rate. Government bond "
        "yields are fetched for about 40 of them; enter the yield manually for the rest.",
    )
    erp = st.slider("Equity risk premium (%)", 0.0, 15.0, DEFAULT_ERP, 0.1, format="%.1f%%") / 100
    debt_share = (
        st.slider("Target debt share, D / (D + E) (%)", 0, 90, DEFAULT_DEBT_SHARE, 1, format="%d%%")
        / 100
    )
    tax_choice = st.radio(
        "Project tax rate",
        [US, "Selected country"],
        horizontal=True,
        key="tax_choice",
        help="The same tax rate is used for both currencies: to re-lever beta and "
        "for the interest tax shield.",
    )

    st.header("Manual overrides")
    st.caption("Switch on to replace fetched data with your own input.")

    def override(label: str, fetched: float | None, key: str, step: float = 0.05,
                 max_value: float = 100.0, force: bool = False) -> tuple[float, bool]:
        """Toggle + number input (in %). Returns (decimal value, is_manual)."""
        on = st.toggle(label, key=f"{key}_on", value=force, disabled=force)
        if on or force:
            default = fetched * 100 if fetched is not None else 0.0
            value = st.number_input(
                f"{label} (%)", min_value=-5.0, max_value=max_value, value=round(default, 2),
                step=step, format="%.2f", key=f"{key}_val", label_visibility="collapsed",
            )
            return value / 100, True
        return fetched, False

    beta_on = st.toggle("Unlevered beta", key="beta_on")
    if beta_on:
        unlevered_beta = st.number_input(
            "Unlevered beta", min_value=0.0, max_value=5.0,
            value=round(float(betas.loc[industry, "unlevered_beta"]), 2), step=0.05,
            format="%.2f", label_visibility="collapsed",
        )
    else:
        unlevered_beta = float(betas.loc[industry, "unlevered_beta"])

    tax_country = US if tax_choice == US else country
    tax_fetched = tax_rates[tax_country]["rate"]
    tax_rate, tax_manual = override("Corporate tax rate", tax_fetched, "tax", step=0.5, max_value=99.0)

    usd_spread, usd_spread_manual = override("USD BBB spread", usd_bbb_fetched, "usd_spread")

    rf_usd, rf_usd_manual = override(
        "U.S. government bond yield", yields[US]["yield"], "rf_usd"
    )

    is_us = country == US
    if is_us:
        rf_for, rf_for_manual = rf_usd, rf_usd_manual
        st.toggle(f"{country} government bond yield", value=rf_usd_manual, disabled=True,
                  help="Same as the U.S. yield while the United States is selected.")
    else:
        has_yield = country in yields
        if not has_yield:
            st.warning(f"No government bond yield available for {country} – please enter one.")
        rf_for, rf_for_manual = override(
            f"{country} government bond yield",
            yields[country]["yield"] if has_yield else rf_usd,
            f"rf_for_{country}",
            force=not has_yield,
        )

    spread_auto = auto_foreign_spread(usd_spread, rf_usd, rf_for)
    for_spread_on = st.toggle(f"{country} BBB spread", key="for_spread_on")
    if for_spread_on:
        for_spread = st.number_input(
            "Foreign BBB spread (%)", min_value=0.0, max_value=50.0,
            value=round(spread_auto * 100, 2), step=0.05, format="%.2f",
            label_visibility="collapsed",
        ) / 100
    else:
        for_spread = spread_auto
        st.caption(f"Auto-calculated: **{pct(spread_auto)}**")

# --------------------------------------------------------------------------
# Calculations
# --------------------------------------------------------------------------
usd = cost_of_capital(unlevered_beta, tax_rate, debt_share, erp, rf_usd, usd_spread)
loc = cost_of_capital(unlevered_beta, tax_rate, debt_share, erp, rf_for, for_spread, rf_usd=rf_usd)

usd_label = "USD"
loc_label = f"{country} currency" if country != US else "United States currency (USD)"

# --------------------------------------------------------------------------
# Header
# --------------------------------------------------------------------------
title_col, refresh_col = st.columns([5, 1], vertical_alignment="bottom")
with title_col:
    st.title("🌍 International Cost of Capital")
    st.caption(
        "Cost of equity, cost of debt and WACC for a project, in U.S. dollars and "
        "in the currency of the selected country."
    )
with refresh_col:
    if st.button("🔄 Refresh data", width='stretch',
                 help="Re-download all data from the sources below."):
        get_data.clear()
        st.rerun()

stale = [k for k, v in data.items() if not v["live"]]
if stale:
    st.warning(
        "Live fetch failed for: "
        + ", ".join(data[k]["source"].split(" – ")[0] + f" ({k})" for k in stale)
        + ". Showing the bundled snapshot for these – see *Data sources* below."
    )

# --------------------------------------------------------------------------
# Results side by side
# --------------------------------------------------------------------------
st.markdown(
    f"### {industry} · {flag(tax_rates[country].get('iso3'))} {country}", unsafe_allow_html=True
)

tax_note = "manual input" if tax_manual else f"{tax_country}, OECD {tax_rates[tax_country]['year']}"
i1, i2, i3, i4 = st.columns(4)
i1.metric("Unlevered beta" + (" (manual)" if beta_on else ""), f"{unlevered_beta:.2f}")
i2.metric("Re-levered beta", f"{usd['levered_beta']:.2f}")
i3.metric(f"Project tax rate ({tax_note})", pct(tax_rate))
i4.metric("Debt / Equity share", f"{debt_share:.0%} / {1 - debt_share:.0%}")

left, right = st.columns(2, gap="large")
flags = (flag("USA"), flag(tax_rates[country].get("iso3")))
for col, label, res, flag_icon in ((left, usd_label, usd, flags[0]), (right, loc_label, loc, flags[1])):
    with col, st.container(border=True):
        st.markdown(f"### {flag_icon} {label}", unsafe_allow_html=True)
        m1, m2, m3 = st.columns(3)
        delta = None if label == usd_label or is_us else f"{(res['wacc'] - usd['wacc']) * 100:+.2f} pp vs USD"
        m1.metric("WACC", pct(res["wacc"]), delta, delta_color="off", delta_arrow="off")
        m2.metric("Cost of equity", pct(res["cost_equity"]))
        m3.metric("Cost of debt (pre-tax)", pct(res["cost_debt"]))

rows = [
    ("Government bond yield (risk-free rate)", "risk_free", pct),
    ("Re-levered beta", "levered_beta", lambda x: f"{x:.2f}"),
    ("Equity risk premium (USD CAPM)", None, lambda _: pct(erp)),
    ("Cost of equity", "cost_equity", pct),
    ("BBB borrowing spread", "spread", pct),
    ("Cost of debt (pre-tax)", "cost_debt", pct),
    ("Project tax rate", None, lambda _: pct(tax_rate)),
    ("Cost of debt (after tax)", "after_tax_cost_debt", pct),
    ("Debt share", None, lambda _: pct(debt_share, 0)),
    ("WACC", "wacc", pct),
]
detail = pd.DataFrame(
    {
        "Component": [r[0] for r in rows],
        usd_label: [r[2](usd.get(r[1])) for r in rows],
        loc_label: [r[2](loc.get(r[1])) for r in rows],
    }
)
st.dataframe(detail, hide_index=True, width='stretch')

if is_us:
    st.caption("The United States is selected as the target country, so both columns are identical.")

results_csv = pd.DataFrame(
    {
        "Item": ["Industry", "Target country", "Unlevered beta", "Project tax rate",
                 "Tax rate basis", "Equity risk premium", "Debt share"]
        + [r[0] for r in rows if r[1]],
        "USD": [industry, country, unlevered_beta, tax_rate, tax_note, erp, debt_share]
        + [usd[r[1]] for r in rows if r[1]],
        loc_label: [industry, country, unlevered_beta, tax_rate, tax_note, erp, debt_share]
        + [loc[r[1]] for r in rows if r[1]],
    }
)

# --------------------------------------------------------------------------
# Tabs: assumptions, all industries, sources
# --------------------------------------------------------------------------
tab_assume, tab_all, tab_sources = st.tabs(
    ["📘 Main assumptions", "🏭 All-industry comparison", "🗂️ Data sources"]
)

with tab_assume:
    st.markdown(
        f"""
**How the numbers are built**

1. **Beta.** The industry's unlevered beta (Damodaran, U.S. companies) is re-levered
   at the target capital structure: β<sub>L</sub> = β<sub>U</sub> × [1 + (1 − t) × D/E],
   with D/E = {debt_share:.0%} / {1 - debt_share:.0%} = {debt_share / (1 - debt_share):.2f}.
2. **Cost of equity in USD** (CAPM): R<sub>e</sub> = R<sub>f</sub> + β<sub>L</sub> × ERP, with the
   U.S. government yield as R<sub>f</sub> and an equity risk premium of {pct(erp, 1)}.
3. **Cost of equity in the foreign currency**: the USD cost of equity is converted with the
   ratio of government yields, (1 + R<sub>e</sub>*) = (1 + R<sub>e</sub>) × (1 + R<sub>f</sub>*) / (1 + R<sub>f</sub>).
   The adjustment reflects the currency's expected depreciation (Fisher equation and relative PPP).
4. **Cost of debt** = government bond yield of the currency + BBB borrowing spread.
   The USD spread is Damodaran's Baa2/BBB default spread for large non-financial service firms.
5. **Foreign BBB spread (auto).** Unless overridden, the same factor is applied to the spread:
   s* = s × (1 + R<sub>f</sub>*) / (1 + R<sub>f</sub>), so the foreign-currency borrowing rate is the
   converted USD borrowing rate.
6. **WACC** = (1 − d) × R<sub>e</sub> + d × R<sub>d</sub> × (1 − τ), computed in each currency. The **same project tax
   rate, debt share and equity risk premium** apply in both currencies; the tax rate is
   either the U.S. or the selected country's combined statutory corporate rate (switch in the sidebar).

**What to keep in mind**

- 10-year government bond yields stand in for the risk-free rate in each currency. For
  countries with meaningful sovereign default risk, the local yield includes a default
  premium, which overstates the local-currency risk-free rate.
- No separate country equity premium is added, and currency risk is treated as
  diversifiable (no extra premium).
- Target leverage stays constant, interest deductions are fully usable, and re-levering
  assumes a zero debt beta.
- Industry betas are averages of U.S.-listed firms and are assumed to apply to the project
  regardless of where it is located.
- Tax rates are statutory (central + sub-central government), not effective rates.
""",
        unsafe_allow_html=True,
    )

with tab_all:
    comp = betas[["n_firms", "unlevered_beta"]].copy()
    usd_all = comp["unlevered_beta"].apply(
        lambda b: cost_of_capital(b, tax_rate, debt_share, erp, rf_usd, usd_spread))
    loc_all = comp["unlevered_beta"].apply(
        lambda b: cost_of_capital(b, tax_rate, debt_share, erp, rf_for, for_spread, rf_usd=rf_usd))
    comp["levered_beta"] = usd_all.apply(lambda r: r["levered_beta"])
    comp["ke_usd"] = usd_all.apply(lambda r: r["cost_equity"]) * 100
    comp["wacc_usd"] = usd_all.apply(lambda r: r["wacc"]) * 100
    comp["ke_loc"] = loc_all.apply(lambda r: r["cost_equity"]) * 100
    comp["wacc_loc"] = loc_all.apply(lambda r: r["wacc"]) * 100
    comp = comp.sort_values("wacc_usd", ascending=False).reset_index()

    st.caption(
        f"Every Damodaran industry at the same settings: {pct(debt_share, 0)} debt, "
        f"{pct(erp, 1)} equity risk premium, {pct(tax_rate)} tax rate, target country {country}. "
        "Uses fetched industry betas (a manual beta override applies to the selected industry only)."
    )

    currency_view = st.radio(
        "Chart currency", [usd_label, loc_label], horizontal=True, disabled=is_us,
        label_visibility="collapsed",
    )
    field = "wacc_usd" if currency_view == usd_label else "wacc_loc"
    chart_df = comp[["industry", field]].rename(columns={field: "wacc"})
    chart_df["selected"] = chart_df["industry"] == industry
    chart = (
        alt.Chart(chart_df)
        .mark_bar()
        .encode(
            x=alt.X("wacc:Q", title=f"WACC in {currency_view} (%)"),
            y=alt.Y("industry:N", sort="-x", title=None, axis=alt.Axis(labelLimit=260)),
            color=alt.condition(alt.datum.selected, alt.value("#d62728"), alt.value("#9ecae1")),
            tooltip=[alt.Tooltip("industry:N", title="Industry"),
                     alt.Tooltip("wacc:Q", title="WACC (%)", format=".2f")],
        )
        .properties(height=24 * len(chart_df))
    )
    st.altair_chart(chart, width='stretch')

    table = comp.rename(
        columns={
            "industry": "Industry", "n_firms": "Firms", "unlevered_beta": "Unlevered beta",
            "levered_beta": "Re-levered beta", "ke_usd": "Cost of equity – USD (%)",
            "wacc_usd": "WACC – USD (%)", "ke_loc": f"Cost of equity – {loc_label} (%)",
            "wacc_loc": f"WACC – {loc_label} (%)",
        }
    )
    if is_us:
        table = table.iloc[:, :6]
    st.dataframe(
        table.style.format(precision=2).apply(
            lambda r: ["font-weight: bold; background-color: rgba(214,39,40,0.15)"
                       if r["Industry"] == industry else ""] * len(r), axis=1),
        hide_index=True, width='stretch', height=420,
    )

with tab_sources:
    def value_note(key: str) -> str:
        if key == "betas":
            return f"{len(betas)} industries; {industry}: βU {betas.loc[industry, 'unlevered_beta']:.2f}"
        if key == "bbb_spread":
            return f"Baa2/BBB spread {pct(usd_bbb_fetched)}"
        if key == "tax_rates":
            parts = [f"{US} {pct(tax_rates[US]['rate'])} ({tax_rates[US]['year']})"]
            if not is_us:
                parts.append(f"{country} {pct(tax_rates[country]['rate'])} ({tax_rates[country]['year']})")
            return "; ".join(parts)
        parts = [f"{US} {pct(yields[US]['yield'])} ({yields[US]['period']})"]
        if not is_us:
            parts.append(
                f"{country} {pct(yields[country]['yield'])} ({yields[country]['period']})"
                if country in yields else f"{country}: not available"
            )
        return "; ".join(parts)

    names = {
        "betas": "Industry betas", "bbb_spread": "USD BBB spread",
        "tax_rates": "Corporate tax rates", "bond_yields": "Government bond yields",
    }
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Data": names[k],
                    "Source": v["source"],
                    "Data as of": v["as_of"],
                    "Fetched": v["fetched_at"],
                    "Status": "✅ live" if v["live"] else "⚠️ bundled snapshot",
                    "Values in use": value_note(k),
                    "Link": v["url"],
                }
                for k, v in data.items()
            ]
        ),
        hide_index=True, width='stretch',
        column_config={"Link": st.column_config.LinkColumn(display_text="open")},
    )
    for k in stale:
        st.caption(f"⚠️ {names[k]}: live fetch failed ({data[k]['error']}).")
    st.caption(
        "Corporate tax rates are the combined (central + sub-central) statutory rates from the "
        "dataset behind the OECD Corporate Tax Statistics chapter "
        f"[Statutory corporate income tax rates]({data['tax_rates'].get('report_url', ds.OECD_TAX_REPORT_URL)}), "
        "read through the OECD data API so the latest year is used. "
        "Manual overrides in the sidebar take precedence over all fetched values."
    )

# --------------------------------------------------------------------------
# Downloads
# --------------------------------------------------------------------------
st.divider()
d1, d2, _ = st.columns([1, 1, 2])
slug = f"{industry}_{country}".replace(" ", "_").replace("/", "-").replace("&", "and")
d1.download_button(
    "⬇️ Download results (CSV)", results_csv.to_csv(index=False).encode("utf-8"),
    file_name=f"cost_of_capital_{slug}.csv", mime="text/csv", width='stretch',
)
d2.download_button(
    "⬇️ Download all industries (CSV)", table.to_csv(index=False).encode("utf-8"),
    file_name=f"all_industries_{country.replace(' ', '_')}.csv", mime="text/csv",
    width='stretch',
)
