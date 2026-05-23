from __future__ import annotations

import logging
from datetime import datetime

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def forecast_balance(
    transactions: list[dict],
    periods: int = 30,
) -> dict:
    """Forecast end-of-month balance using Prophet (or linear fallback).

    Args:
        transactions: list of dicts with 'date' and 'amount' keys
        periods: number of days to forecast

    Returns:
        dict with predicted_balance, bounds, forecast_error, daily_forecast

    """
    if len(transactions) < 5:
        return _empty_forecast()

    try:
        return _prophet_forecast(transactions, periods)
    except Exception as exc:
        logger.warning("Prophet failed, using linear fallback: %s", exc)
        return _linear_fallback(transactions, periods)


def _prophet_forecast(transactions: list[dict], periods: int) -> dict:
    """Full Prophet time-series forecast."""
    from prophet import Prophet

    df = _prepare_dataframe(transactions)
    if df.empty or len(df) < 5:
        return _linear_fallback(transactions, periods)

    model = Prophet(
        interval_width=0.9,
        daily_seasonality=False,
        weekly_seasonality=True,
        yearly_seasonality=False,
    )
    model.fit(df)

    future = model.make_future_dataframe(periods=periods)
    forecast = model.predict(future)

    last_row = forecast.iloc[-1]
    predicted = float(last_row["yhat"])
    lower = float(last_row["yhat_lower"])
    upper = float(last_row["yhat_upper"])

    interval_width = upper - lower
    forecast_error = (
        min(abs(interval_width / predicted), 1.0) if predicted != 0 else 0.5
    )

    daily = forecast.tail(periods)[["ds", "yhat"]].rename(
        columns={"ds": "date", "yhat": "predicted"},
    )
    daily["date"] = daily["date"].dt.strftime("%Y-%m-%d")
    daily["predicted"] = daily["predicted"].round(2)

    return {
        "predicted_balance": round(predicted, 2),
        "lower_bound": round(lower, 2),
        "upper_bound": round(upper, 2),
        "forecast_error": round(forecast_error, 4),
        "daily_forecast": daily.to_dict("records"),
    }


def _linear_fallback(transactions: list[dict], periods: int) -> dict:
    """Simple linear extrapolation when Prophet is unavailable or data is thin."""
    df = _prepare_dataframe(transactions)
    if df.empty:
        return _empty_forecast()

    x = np.arange(len(df))
    y = df["y"].values.astype(float)

    if len(x) < 2:
        last_val = float(y[-1])
        return {
            "predicted_balance": last_val,
            "lower_bound": last_val * 0.8,
            "upper_bound": last_val * 1.2,
            "forecast_error": 0.5,
            "daily_forecast": [],
        }

    coeffs = np.polyfit(x, y, 1)
    future_x = len(df) + periods
    predicted = float(np.polyval(coeffs, future_x))
    std = float(np.std(y))

    return {
        "predicted_balance": round(predicted, 2),
        "lower_bound": round(predicted - 1.645 * std, 2),
        "upper_bound": round(predicted + 1.645 * std, 2),
        "forecast_error": round(
            min(std / abs(predicted), 1.0) if predicted != 0 else 0.5,
            4,
        ),
        "daily_forecast": [],
    }


def _prepare_dataframe(transactions: list[dict]) -> pd.DataFrame:
    """Convert transactions to daily cumulative balance for Prophet (ds, y)."""
    if not transactions:
        return pd.DataFrame(columns=["ds", "y"])

    records = []
    for txn in transactions:
        date = txn["date"]
        if isinstance(date, str):
            date = datetime.fromisoformat(date)
        records.append({"ds": date.date(), "amount": txn["amount"]})

    df = pd.DataFrame(records)
    daily = df.groupby("ds")["amount"].sum().reset_index()
    daily.columns = ["ds", "y"]
    daily = daily.sort_values("ds")
    daily["y"] = daily["y"].cumsum()
    daily["ds"] = pd.to_datetime(daily["ds"])

    return daily


def _empty_forecast() -> dict:
    return {
        "predicted_balance": 0.0,
        "lower_bound": 0.0,
        "upper_bound": 0.0,
        "forecast_error": 1.0,
        "daily_forecast": [],
    }
