"""Data retrieval for the International Cost of Capital app.

Every fetcher returns a dict with the parsed data plus `source`, `url`,
`as_of` (the date the provider attaches to the data) and `fetched_at`.
If a live fetch fails, the bundled snapshot (data/snapshot.json) is used and
the dict carries `live=False` plus the error message.

Run `python data_sources.py` to rebuild the snapshot from the live sources.
"""

from __future__ import annotations

import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

SNAPSHOT_PATH = Path(__file__).parent / "data" / "snapshot.json"

BETAS_URL = "https://pages.stern.nyu.edu/~adamodar/pc/datasets/betas.xls"
RATINGS_URL = "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/ratings.html"
OECD_TAX_REPORT_URL = (
    "https://www.oecd.org/en/publications/corporate-tax-statistics-2024_9c27d6e8-en/"
    "full-report/statutory-corporate-income-tax-rates_440f9286.html"
)
OECD_TAX_API_URL = (
    "https://sdmx.oecd.org/public/rest/data/OECD.CTP.TPS,DSD_TAX_CIT@DF_CIT,/all"
)
OECD_TAX_EXPLORER_URL = (
    "https://data-explorer.oecd.org/vis?df[ds]=dsDisseminateFinalDMZ"
    "&df[id]=DSD_TAX_CIT%40DF_CIT&df[ag]=OECD.CTP.TPS"
)
OECD_YIELD_API_URL = (
    "https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_FINMARK,/"
    ".M.IRLT......"
)
OECD_YIELD_EXPLORER_URL = (
    "https://data-explorer.oecd.org/vis?df[ds]=dsDisseminateFinalDMZ"
    "&df[id]=DSD_STES%40DF_FINMARK&df[ag]=OECD.SDD.STES"
)

HEADERS = {"User-Agent": "Mozilla/5.0 (cost-of-capital-app)"}
CSV_HEADERS = {**HEADERS, "Accept": "application/vnd.sdmx.data+csv; charset=utf-8; labels=both"}
TIMEOUT = 45
US = "United States"

# OECD labels that differ from everyday country names.
COUNTRY_RENAMES = {
    "China (People’s Republic of)": "China",
    "Hong Kong (China)": "Hong Kong",
    "Macau (China)": "Macau",
    "Korea": "South Korea",
    "Slovak Republic": "Slovakia",
    "Türkiye": "Turkey",
}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _get(url: str, headers: dict = HEADERS, params: dict | None = None) -> requests.Response:
    resp = requests.get(url, headers=headers, params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp


def _country(label: str) -> str:
    name = label.split(": ", 1)[1] if ": " in label else label
    return COUNTRY_RENAMES.get(name, name)


def _oecd_csv(url: str, start_period: str) -> pd.DataFrame:
    resp = _get(
        url,
        headers=CSV_HEADERS,
        params={"startPeriod": start_period, "dimensionAtObservation": "AllDimensions"},
    )
    df = pd.read_csv(io.StringIO(resp.content.decode("utf-8")))
    df.columns = [c.split(":")[0] for c in df.columns]
    return df


# --------------------------------------------------------------------------
# Individual sources
# --------------------------------------------------------------------------
def fetch_betas() -> dict:
    """Industry betas (US companies) from Damodaran's betas.xls."""
    resp = _get(BETAS_URL)
    raw = pd.read_excel(io.BytesIO(resp.content), sheet_name="Industry Averages", header=None)

    as_of = None
    for _, row in raw.head(9).iterrows():
        if str(row[0]).strip().lower().startswith("date updated"):
            as_of = pd.to_datetime(row[1]).strftime("%Y-%m-%d")

    header_idx = raw.index[raw[0].astype(str).str.strip() == "Industry Name"][0]
    header = [str(h).strip() for h in raw.loc[header_idx]]
    table = raw.loc[header_idx + 1 :].copy()
    table.columns = header
    table = table[table["Industry Name"].notna()]

    def col(prefix: str) -> str:
        return next(h for h in header if h.lower().startswith(prefix.lower()))

    out = pd.DataFrame(
        {
            "industry": table["Industry Name"].astype(str).str.strip(),
            "n_firms": pd.to_numeric(table[col("Number of firms")], errors="coerce"),
            "levered_beta": pd.to_numeric(table[col("Beta")], errors="coerce"),
            "de_ratio": pd.to_numeric(table[col("D/E")], errors="coerce"),
            "unlevered_beta": pd.to_numeric(table[col("Unlevered beta")], errors="coerce"),
        }
    ).dropna(subset=["unlevered_beta"])
    if len(out) < 50:
        raise ValueError(f"Only {len(out)} industries parsed from betas.xls")

    return {
        "source": "Aswath Damodaran (NYU Stern) – Betas by Sector (US)",
        "url": BETAS_URL,
        "as_of": as_of or "n/a",
        "fetched_at": _now(),
        "industries": out.to_dict("records"),
    }


def fetch_bbb_spread() -> dict:
    """Baa2/BBB default spread for large non-financial service firms."""
    html = _get(RATINGS_URL).content.decode("latin-1")
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html).replace("&nbsp;", " "))

    # Each table row lists the large non-financial firm columns first, then the
    # financial service firm columns, so the first match is the one we want.
    match = re.search(r"Baa2/BBB\s+([\d.]+)\s*%", text)
    if not match:
        raise ValueError("Baa2/BBB spread not found on ratings page")
    spread = float(match.group(1)) / 100
    if not 0 < spread < 0.15:
        raise ValueError(f"Implausible BBB spread parsed: {spread}")

    as_of = re.search(r"Data used is as of\s+([A-Za-z]+\s+\d{4})", text)
    return {
        "source": "Aswath Damodaran (NYU Stern) – Ratings, Interest Coverage Ratios "
        "and Default Spread (Baa2/BBB, large non-financial service firms)",
        "url": RATINGS_URL,
        "as_of": as_of.group(1) if as_of else "n/a",
        "fetched_at": _now(),
        "spread": spread,
    }


def fetch_tax_rates() -> dict:
    """Combined (central + sub-central) statutory corporate income tax rates.

    This is the dataset behind the 'Statutory corporate income tax rates'
    chapter of OECD Corporate Tax Statistics. The report page itself sits
    behind a browser check, so the official OECD data API is used instead,
    which also carries more recent years than the 2024 report.
    """
    year = datetime.now().year
    df = _oecd_csv(OECD_TAX_API_URL, str(year - 3))
    df = df[
        df["MEASURE"].str.startswith("CIT_C:")
        & df["TARGETING"].str.startswith("ST:")
        & df["OBS_VALUE"].notna()
    ]
    latest = df.sort_values("TIME_PERIOD").groupby("REF_AREA").tail(1)
    rates = {
        _country(r.REF_AREA): {
            "rate": float(r.OBS_VALUE) / 100,
            "year": int(r.TIME_PERIOD),
            "iso3": r.REF_AREA.split(":")[0],
        }
        for r in latest.itertuples()
    }
    if US not in rates or len(rates) < 30:
        raise ValueError("OECD tax data incomplete")
    return {
        "source": "OECD Corporate Tax Statistics – combined statutory corporate "
        "income tax rate (OECD Data Explorer API)",
        "url": OECD_TAX_EXPLORER_URL,
        "report_url": OECD_TAX_REPORT_URL,
        "as_of": str(max(v["year"] for v in rates.values())),
        "fetched_at": _now(),
        "rates": rates,
    }


def fetch_bond_yields() -> dict:
    """Long-term (10-year) government bond yields, latest monthly average."""
    start = (pd.Timestamp.now() - pd.DateOffset(months=12)).strftime("%Y-%m")
    df = _oecd_csv(OECD_YIELD_API_URL, start)
    df = df[df["OBS_VALUE"].notna() & ~df["REF_AREA"].str.startswith("EA")]
    latest = df.sort_values("TIME_PERIOD").groupby("REF_AREA").tail(1)
    yields = {
        _country(r.REF_AREA): {"yield": float(r.OBS_VALUE) / 100, "period": str(r.TIME_PERIOD)}
        for r in latest.itertuples()
    }
    if US not in yields:
        raise ValueError("OECD yield data has no United States series")
    return {
        "source": "OECD Main Economic Indicators – long-term (10-year) government "
        "bond yields, monthly average",
        "url": OECD_YIELD_EXPLORER_URL,
        "as_of": max(v["period"] for v in yields.values()),
        "fetched_at": _now(),
        "yields": yields,
    }


FETCHERS = {
    "betas": fetch_betas,
    "bbb_spread": fetch_bbb_spread,
    "tax_rates": fetch_tax_rates,
    "bond_yields": fetch_bond_yields,
}


# --------------------------------------------------------------------------
# Loading with snapshot fallback
# --------------------------------------------------------------------------
def load_snapshot() -> dict:
    return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))


def load_all() -> dict:
    """Fetch every source live; fall back per-source to the bundled snapshot."""
    data, snapshot = {}, None
    for key, fetcher in FETCHERS.items():
        try:
            data[key] = {**fetcher(), "live": True}
        except Exception as exc:  # network, parsing or layout change
            snapshot = snapshot or load_snapshot()
            data[key] = {**snapshot[key], "live": False, "error": f"{type(exc).__name__}: {exc}"}
    return data


if __name__ == "__main__":
    fresh = {key: fetcher() for key, fetcher in FETCHERS.items()}
    SNAPSHOT_PATH.parent.mkdir(exist_ok=True)
    SNAPSHOT_PATH.write_text(json.dumps(fresh, indent=1, ensure_ascii=False), encoding="utf-8")
    print(
        f"Snapshot written: {len(fresh['betas']['industries'])} industries, "
        f"BBB {fresh['bbb_spread']['spread']:.2%}, "
        f"{len(fresh['tax_rates']['rates'])} tax rates, "
        f"{len(fresh['bond_yields']['yields'])} bond yields"
    )
