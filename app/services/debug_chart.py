from io import BytesIO
import os
import tempfile

os.environ.setdefault("MPLCONFIGDIR", tempfile.gettempdir())

import matplotlib

matplotlib.use("Agg")

from matplotlib import pyplot as plt
from matplotlib import dates as mdates

from app.schemas.forecast import ForecastResponse


def render_forecast_png(forecast: ForecastResponse) -> bytes:
    figure, (price_axis, volume_axis) = plt.subplots(
        2,
        1,
        figsize=(15, 10),
        gridspec_kw={"height_ratios": [3, 1], "hspace": 0.05},
        constrained_layout=True,
        sharex=True,
    )

    history_dates = [point.date for point in forecast.history]
    history_prices = [point.close for point in forecast.history]
    history_volumes = [point.volume for point in forecast.history]
    forecast_dates = [point.date for point in forecast.forecast]
    forecast_prices = [point.median for point in forecast.forecast]
    forecast_lows = [point.low for point in forecast.forecast]
    forecast_highs = [point.high for point in forecast.forecast]
    forecast_volumes = [point.volume for point in forecast.forecast]

    price_axis.plot(
        history_dates,
        history_prices,
        color="#4169e1",
        linewidth=1.6,
        label="Historical Price",
        zorder=3,
    )
    price_axis.plot(
        forecast_dates,
        forecast_prices,
        color="#ff8c00",
        linewidth=1.6,
        label="Mean Forecast",
        zorder=4,
    )
    price_axis.fill_between(
        forecast_dates,
        forecast_lows,
        forecast_highs,
        color="#ff8c00",
        alpha=0.18,
        label="Forecast Range (Min-Max)",
        zorder=2,
    )

    forecast_start = forecast_dates[0]
    for axis in (price_axis, volume_axis):
        axis.axvline(
            forecast_start,
            color="red",
            linestyle="--",
            linewidth=1.4,
            alpha=0.85,
            zorder=5,
        )
        axis.grid(True, linestyle="--", linewidth=0.45, color="#9a9a9a", alpha=0.7)

    bar_width = _date_bar_width(history_dates + forecast_dates)
    volume_axis.bar(
        history_dates,
        history_volumes,
        width=bar_width,
        color="#87ceeb",
        edgecolor="none",
        label="Historical Volume",
        zorder=3,
    )
    volume_axis.bar(
        forecast_dates,
        forecast_volumes,
        width=bar_width,
        color="#f4a261",
        edgecolor="none",
        label="Mean Forecasted Volume",
        zorder=3,
    )

    title_horizon = "Day" if forecast.days == 1 else "Days"
    figure.suptitle(
        f"{forecast.ticker} Probabilistic Price & Volume Forecast (Next {forecast.days} {title_horizon})",
        fontsize=18,
        fontweight="bold",
    )
    price_axis.set_ylabel("Price (USD)")
    volume_axis.set_ylabel("Volume")
    volume_axis.set_xlabel("Time (UTC)")

    price_axis.legend(loc="upper left", frameon=True)
    volume_axis.legend(loc="upper left", frameon=True)
    volume_axis.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    volume_axis.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=6, maxticks=10))
    plt.setp(volume_axis.get_xticklabels(), rotation=30, ha="right")

    chart_dates = history_dates + forecast_dates
    first_date = min(chart_dates)
    last_date = max(chart_dates)
    padding = max(bar_width * 3, 1.0)
    price_axis.set_xlim(
        mdates.date2num(first_date) - padding,
        mdates.date2num(last_date) + padding,
    )

    buffer = BytesIO()
    figure.savefig(buffer, format="png", dpi=120)
    plt.close(figure)
    return buffer.getvalue()


def _date_bar_width(dates) -> float:
    if len(dates) < 2:
        return 0.6

    numeric_dates = sorted(mdates.date2num(date_value) for date_value in dates)
    gaps = [
        current - previous
        for previous, current in zip(numeric_dates, numeric_dates[1:])
        if current > previous
    ]
    if not gaps:
        return 0.6

    return min(gaps) * 0.65
