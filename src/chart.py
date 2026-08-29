import logging
import os
from typing import Optional, Sequence

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from comparison_engine import ComparisonResult

logger = logging.getLogger("octobot.chart")

STANDING_COLOR = "#9A3B3B"
CONSUMPTION_COLOR = "#632626"


def _chart_path() -> str:
    for directory in ("/data", "/app/logs", "/tmp"):
        if os.path.isdir(directory) and os.access(directory, os.W_OK):
            return os.path.join(directory, "tariff_comparison.jpg")
    return "/tmp/tariff_comparison.jpg"


def _pounds(value: float) -> str:
    return f"£{value:.2f}"


def _label(ax, x: float, y: float, text: str, va: str = "center", ha: str = "center") -> None:
    ax.text(x, y, text, ha=ha, va=va, color="white", fontsize=9, clip_on=True)


def _draw_cost_bars(
    ax,
    labels: Sequence[str],
    standing_charges: Sequence[float],
    consumption_costs: Sequence[float],
    total_costs: Sequence[float],
) -> None:
    xs = list(range(len(labels)))
    has_negative_total = any(total < 0 for total in total_costs)

    standing_bars = ax.bar(xs, standing_charges, color=STANDING_COLOR, zorder=2)

    positive_consumption = [cost if cost > 0 else 0 for cost in consumption_costs]
    ax.bar(xs, positive_consumption, bottom=standing_charges, color=CONSUMPTION_COLOR, zorder=3)

    hatch_heights = []
    hatch_bottoms = []
    below_zero = []
    for standing, consumption, total in zip(standing_charges, consumption_costs, total_costs):
        if consumption >= 0:
            hatch_heights.append(0)
            hatch_bottoms.append(0)
            below_zero.append(0)
            continue
        # Hatch the standing charge from the net remainder (or 0) up to the full S/C.
        hatch_bottom = max(total, 0)
        hatch_heights.append(max(standing - hatch_bottom, 0))
        hatch_bottoms.append(hatch_bottom)
        below_zero.append(total if total < 0 else 0)

    ax.bar(
        xs,
        hatch_heights,
        bottom=hatch_bottoms,
        facecolor=CONSUMPTION_COLOR,
        edgecolor="white",
        hatch="///",
        linewidth=0.6,
        zorder=4,
    )
    ax.bar(xs, below_zero, color=CONSUMPTION_COLOR, zorder=3)

    visual_tops = [standing + max(consumption, 0) for standing, consumption in zip(standing_charges, consumption_costs)]
    visual_bottoms = [min(0, total) for total in total_costs]
    y_max = max(visual_tops) if visual_tops else 1
    y_min = min(visual_bottoms) if visual_bottoms else 0
    headroom = max(abs(y_max) * 0.22, abs(y_min) * 0.35, 0.18)
    ax.set_ylim(y_min - (headroom if y_min < 0 else 0), y_max + headroom)
    span = ax.get_ylim()[1] - ax.get_ylim()[0]
    min_inside = span * 0.08
    total_offset = span * 0.04

    if has_negative_total or any(cost < 0 for cost in consumption_costs):
        ax.axhline(0, color="white", linewidth=0.8, zorder=1)

    for x, bar, standing, consumption, total, hatch_h, hatch_b in zip(
        xs, standing_bars, standing_charges, consumption_costs, total_costs, hatch_heights, hatch_bottoms
    ):
        cx = bar.get_x() + bar.get_width() / 2
        if consumption >= 0:
            if standing >= min_inside:
                _label(ax, cx, standing / 2, _pounds(standing))
            if consumption >= min_inside:
                _label(ax, cx, standing + consumption / 2, _pounds(consumption))
            _label(ax, cx, total + total_offset, _pounds(total), va="bottom")
            continue

        remainder = hatch_b  # unhatched S/C when total > 0, else 0
        if remainder >= min_inside:
            _label(ax, cx, remainder / 2, _pounds(standing))
        elif standing >= min_inside:
            _label(ax, cx, standing / 2, _pounds(standing))

        if total < 0:
            if abs(total) >= min_inside:
                _label(ax, cx, total / 2, _pounds(consumption))
            elif hatch_h >= min_inside:
                _label(ax, cx, hatch_b + hatch_h / 2, _pounds(consumption))
            else:
                _label(ax, cx + 0.42, (total / 2) if total else standing / 2, _pounds(consumption), ha="left")
            _label(ax, cx, total - total_offset, _pounds(total), va="top")
        else:
            if hatch_h >= min_inside:
                _label(ax, cx, hatch_b + hatch_h / 2, _pounds(consumption))
            elif hatch_h > 0:
                _label(ax, cx + 0.42, hatch_b + hatch_h / 2, _pounds(consumption), ha="left")
            _label(ax, cx, standing + total_offset, _pounds(total), va="bottom")

    ax.set_ylabel("Cost (£)", color="white")
    ax.set_xticks(xs)
    ax.set_xticklabels(list(labels), rotation=45, ha="right", color="white")
    ax.tick_params(colors="white")
    ax.grid(False, axis="x")


def create_tariff_comparison_chart(result: ComparisonResult) -> Optional[str]:
    """Render a stacked bar chart of standing charge vs consumption cost per tariff."""
    valid = [comparison for comparison in result.all_comparisons if comparison.is_valid]
    if not valid:
        logger.warning("No valid tariff comparisons available to chart")
        return None

    labels = [comparison.tariff.display_name for comparison in valid]
    standing_charges = [comparison.cost_breakdown.standing_charge_pounds for comparison in valid]
    consumption_costs = [comparison.cost_breakdown.consumption_cost_pounds for comparison in valid]
    total_costs = [comparison.cost_breakdown.total_cost_pounds for comparison in valid]

    plt.style.use("dark_background")
    fig, ax = plt.subplots(figsize=(8, 6))
    fig.patch.set_facecolor("#121212")
    ax.set_facecolor("#121212")
    _draw_cost_bars(ax, labels, standing_charges, consumption_costs, total_costs)
    plt.tight_layout()

    path = _chart_path()
    try:
        fig.savefig(path, format="jpeg", dpi=120, facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.15)
    except ValueError:
        path = os.path.splitext(path)[0] + ".png"
        fig.savefig(path, format="png", dpi=120, facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)

    size = os.path.getsize(path) if os.path.isfile(path) else 0
    if size <= 0:
        logger.error(f"Comparison chart was not written to {path}")
        return None

    logger.info(f"Wrote comparison chart ({size} bytes) to {path}")
    return path
