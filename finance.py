"""Cost of capital calculations (all rates as decimals)."""

from __future__ import annotations


def relever_beta(unlevered_beta: float, tax_rate: float, debt_share: float) -> float:
    """Hamada: beta_L = beta_U * (1 + (1 - t) * D/E), with D/E = w / (1 - w)."""
    return unlevered_beta * (1 + (1 - tax_rate) * debt_share / (1 - debt_share))


def auto_foreign_spread(usd_spread: float, rf_usd: float, rf_foreign: float) -> float:
    """Foreign-currency BBB spread implied by interest rate parity.

    The USD borrowing cost (rf_usd + spread) is converted to the foreign
    currency with the government-yield differential; the spread is what is
    left above the foreign government yield.
    """
    return usd_spread * (1 + rf_foreign) / (1 + rf_usd)


def convert_rate(rate_usd: float, rf_usd: float, rf_foreign: float) -> float:
    """Convert a USD rate to the foreign currency via interest rate parity."""
    return (1 + rate_usd) * (1 + rf_foreign) / (1 + rf_usd) - 1


def cost_of_capital(
    unlevered_beta: float,
    tax_rate: float,
    debt_share: float,
    erp: float,
    rf: float,
    spread: float,
) -> dict:
    """Cost of equity, cost of debt and WACC in the currency of `rf`."""
    beta = relever_beta(unlevered_beta, tax_rate, debt_share)
    cost_equity = rf + beta * erp
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
