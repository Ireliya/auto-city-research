#!/usr/bin/env python3
"""Shared publication styling and export checks for project figures."""

from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from PIL import Image, ImageStat


INK = "#272727"
MUTED = "#666666"
GRID = "#D9DEE3"
BLUE = "#0F4D92"
BLUE_MID = "#4E83B3"
TEAL = "#3B8C88"
ROSE = "#B6435A"
GOLD = "#C78B2C"
NEUTRAL = "#7A7A7A"
LIGHT_NEUTRAL = "#D5D8DB"

EVENT_COLORS = {
    "Harvey": BLUE,
    "Mexico EQ": NEUTRAL,
    "Palu": TEAL,
    "Santa Rosa": ROSE,
}

EVENT_MARKERS = {
    "Harvey": "o",
    "Mexico EQ": "s",
    "Palu": "^",
    "Santa Rosa": "D",
}

CMAP_BLUE = LinearSegmentedColormap.from_list(
    "urban_blue",
    ["#F5F7F8", "#D7E4ED", "#8DB6D2", "#3D79A8", BLUE],
)
CMAP_ROSE = LinearSegmentedColormap.from_list(
    "urban_rose",
    ["#FAF7F7", "#F0D7DC", "#D894A1", "#BE5C70", "#7F2946"],
)
CMAP_DIVERGING = LinearSegmentedColormap.from_list(
    "urban_diverging",
    ["#2C6EA6", "#A9C9DE", "#F7F7F7", "#E7B4AC", "#A63E43"],
)


def apply_publication_style(font_size: float = 7.2) -> None:
    """Apply a compact, editable, journal-width matplotlib style."""
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"]
    plt.rcParams["svg.fonttype"] = "none"
    plt.rcParams.update(
        {
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "font.size": font_size,
            "axes.titlesize": font_size + 0.8,
            "axes.titleweight": "normal",
            "axes.labelsize": font_size,
            "axes.labelcolor": INK,
            "axes.edgecolor": INK,
            "axes.linewidth": 0.75,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.facecolor": "white",
            "xtick.labelsize": font_size - 0.4,
            "ytick.labelsize": font_size - 0.4,
            "xtick.color": INK,
            "ytick.color": INK,
            "xtick.major.width": 0.65,
            "ytick.major.width": 0.65,
            "legend.fontsize": font_size - 0.4,
            "legend.frameon": False,
            "figure.facecolor": "white",
            "figure.dpi": 160,
            "savefig.facecolor": "white",
            "savefig.bbox": "tight",
            "lines.linewidth": 1.6,
            "lines.markersize": 4.5,
        }
    )


def add_panel_label(
    ax: plt.Axes,
    label: str,
    *,
    x: float = -0.10,
    y: float = 1.06,
    color: str = INK,
) -> None:
    """Add a compact Nature-style lowercase panel label."""
    ax.text(
        x,
        y,
        label,
        transform=ax.transAxes,
        ha="left",
        va="bottom",
        fontsize=8.2,
        fontweight="bold",
        color=color,
        clip_on=False,
    )


def style_numeric_axis(ax: plt.Axes, *, axis: str = "y") -> None:
    """Use restrained major grid lines on one quantitative axis."""
    ax.set_axisbelow(True)
    ax.grid(False)
    ax.grid(axis=axis, color=GRID, linewidth=0.55, alpha=0.9)


def set_heatmap_annotation_contrast(ax: plt.Axes, values) -> None:
    """Switch heatmap annotation text between ink and white by cell value."""
    flat = [float(value) for row in values for value in row]
    if not flat:
        return
    low, high = min(flat), max(flat)
    span = high - low
    for text, value in zip(ax.texts, flat):
        normalized = 0.5 if span == 0 else (value - low) / span
        text.set_color("white" if normalized >= 0.58 else INK)
        text.set_fontsize(6.8)


def add_direct_line_labels(
    ax: plt.Axes,
    frames: list[tuple[str, object]],
    *,
    x_col: str,
    y_col: str,
    x_pad_fraction: float = 0.025,
) -> None:
    """Label line endpoints and reserve a small right margin for the labels."""
    x_min, x_max = ax.get_xlim()
    x_pad = max((x_max - x_min) * x_pad_fraction, 0.01)
    for label, frame in frames:
        if frame.empty:
            continue
        row = frame.sort_values(x_col).iloc[-1]
        ax.text(
            float(row[x_col]) + x_pad,
            float(row[y_col]),
            label,
            color=EVENT_COLORS.get(label, INK),
            fontsize=6.5,
            va="center",
            ha="left",
            clip_on=False,
        )
    ax.set_xlim(x_min, x_max + 5 * x_pad)


def save_publication_figure(
    fig: plt.Figure,
    out_dir: Path,
    basename: str,
    *,
    grayscale: bool = True,
    dpi: int = 600,
) -> dict[str, Path]:
    """Export editable SVG/PDF plus a high-resolution PNG and run basic QA."""
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "svg": out_dir / f"{basename}.svg",
        "pdf": out_dir / f"{basename}.pdf",
        "png": out_dir / f"{basename}.png",
    }
    fig.savefig(outputs["svg"], bbox_inches="tight")
    fig.savefig(outputs["pdf"], bbox_inches="tight")
    fig.savefig(outputs["png"], dpi=dpi, bbox_inches="tight")
    plt.close(fig)

    with Image.open(outputs["png"]) as image:
        rgb = image.convert("RGB")
        width, height = rgb.size
        variation = sum(ImageStat.Stat(rgb.resize((96, 96))).stddev) / 3
        if width < 1200 or height < 700:
            raise RuntimeError(f"Figure preview is too small: {basename}={width}x{height}")
        if variation < 3:
            raise RuntimeError(f"Figure preview appears blank: {basename}")
        if grayscale:
            gray_path = out_dir / f"{basename}_grayscale.png"
            rgb.convert("L").save(gray_path, dpi=(dpi, dpi))
            outputs["grayscale_png"] = gray_path

    svg_text = outputs["svg"].read_text(encoding="utf-8", errors="ignore")
    if "<text" not in svg_text:
        raise RuntimeError(f"SVG text is not editable for {basename}")
    return outputs


def mm_to_inches(value_mm: float) -> float:
    return value_mm / 25.4


def color_for_event(label: str) -> str:
    return EVENT_COLORS.get(label, BLUE_MID)


def marker_for_event(label: str) -> str:
    return EVENT_MARKERS.get(label, "o")


def make_norm(vmin: float, vmax: float) -> mpl.colors.Normalize:
    return mpl.colors.Normalize(vmin=vmin, vmax=vmax)
