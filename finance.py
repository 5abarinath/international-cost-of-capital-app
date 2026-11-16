"""Cost of capital calculations (all rates as decimals)."""

from __future__ import annotations


def relever_beta(unlevered_beta: float, tax_rate: float, debt_share: float) -> float:
    """Hamada: beta_L = beta_U * (1 + (1 - t) * D/E), with D/E = w / (1 - w)."""
    return unlevered_beta * (1 + (1 - tax_rate) * debt_share / (1 - debt_share))


def auto_foreign_spread(usd_spread: float, rf_usd: float, rf_foreign: float) -> float:
    """Foreign-currency BBB spread: s* = s (1 + Rf*) / (1 + Rf)."""
    return usd_spread * (1 + rf_foreign) / (1 + rf_usd)


def convert_rate(rate_usd: float, rf_usd: float, rf_foreign: float) -> float:
    """(1 + R*) = (1 + R) (1 + Rf*) / (1 + Rf)."""
    return (1 + rate_usd) * (1 + rf_foreign) / (1 + rf_usd) - 1


def cost_of_capital(
    unlevered_beta: float,
    tax_rate: float,
    debt_share: float,
    erp: float,
    rf: float,
    spread: float,
    rf_usd: float | None = None,
) -> dict:
    """Cost of equity, cost of debt and WACC in the currency of `rf`.

    For USD, pass only `rf` (the U.S. yield): cost of equity is CAPM.
    For a foreign currency, also pass `rf_usd`: the USD CAPM cost of equity
    is converted with (1 + Re*) = (1 + Re) (1 + Rf*) / (1 + Rf).
    """
    beta = relever_beta(unlevered_beta, tax_rate, debt_share)
    if rf_usd is None:
        cost_equity = rf + beta * erp
    else:
        cost_equity = convert_rate(rf_usd + beta * erp, rf_usd, rf)
    cost_debt = rf + spread
    after_tax_debt = cost_debt * (1 - tax_rate)
    wacc = (1 - debt_share) * cost_equity + debt_share * after_tax_debt
    return {
        "risk_free": rf,
        "levered_beta": beta,
        "cost_equity": cost_equity,
        "spread": spread,
        "cost_debt": cost_debt,
        "after_tax_cost_debt": after_tax_debt,
        "wacc": wacc,
    }
