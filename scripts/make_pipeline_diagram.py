"""Generates the pipeline architecture diagram referenced in paper/main.tex's Introduction
figure -- the target architecture (Section 3.2), clearly marked which stages are implemented
(Section 3.1) vs. not, so the figure itself carries the same honesty the text does.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrow, FancyBboxPatch

matplotlib.use("Agg")

OUT_PATH = Path(__file__).resolve().parent.parent / "paper" / "enterprisesynth_pipeline_diagram.pdf"

BLUE = "#2a78d6"
GREY = "#c3c2b7"
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"

IMPLEMENTED = [
    "OpenAPI\nSpec",
    "1. API Schema\nParser",
    "2. Intent\nGeneration Agent",
    "3. Trajectory\nGeneration Agent",
    "4. Schema\nVerification Engine",
]
NOT_IMPLEMENTED = [
    "(Knowledge\nGraph)",
    "(Planner)",
]


def draw_box(ax, x, y, w, h, text, color, text_color=TEXT_PRIMARY, dashed=False):
    style = "round,pad=0.02"
    box = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle=style,
        linewidth=1.5,
        edgecolor=color,
        facecolor="white" if not dashed else "#f7f7f5",
        linestyle="dashed" if dashed else "solid",
    )
    ax.add_patch(box)
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=9, color=text_color)


def draw_arrow(ax, x1, y, x2):
    ax.add_patch(
        FancyArrow(
            x1, y, x2 - x1, 0, width=0.003, head_width=0.025, head_length=0.015,
            length_includes_head=True, color=TEXT_SECONDARY,
        )
    )


def main() -> None:
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    # Implemented pipeline (top row)
    n = len(IMPLEMENTED)
    box_w, box_h, gap = 0.125, 0.16, 0.028
    out_w = 0.11
    total_w = n * box_w + (n - 1) * gap + gap + out_w
    start_x = (1 - total_w) / 2
    y_top = 0.62

    xs = []
    for i, label in enumerate(IMPLEMENTED):
        x = start_x + i * (box_w + gap)
        xs.append(x)
        color = GREY if i == 0 else BLUE
        draw_box(ax, x, y_top, box_w, box_h, label, color)
        if i > 0:
            draw_arrow(ax, xs[i - 1] + box_w, y_top + box_h / 2, x)

    ax.text(
        start_x, y_top + box_h + 0.06,
        "Implemented system (Section 3.1) -- what Sections 6-8 actually measure",
        fontsize=11, color=TEXT_PRIMARY, weight="bold",
    )

    # Output boxes
    out_x = xs[-1] + box_w + gap
    draw_box(ax, out_x, y_top + 0.09, out_w, 0.08, "SFT\nDataset", BLUE)
    draw_box(ax, out_x, y_top - 0.01, out_w, 0.08, "Evaluation\nDataset", BLUE)
    draw_arrow(ax, xs[-1] + box_w, y_top + 0.13, out_x)
    draw_arrow(ax, xs[-1] + box_w, y_top + 0.03, out_x)

    # Target architecture (bottom row) -- not implemented stages, dashed
    y_bot = 0.18
    draw_box(ax, xs[1], y_bot, box_w, box_h, NOT_IMPLEMENTED[0], GREY, TEXT_SECONDARY, dashed=True)
    draw_box(ax, xs[2], y_bot, box_w, box_h, NOT_IMPLEMENTED[1], GREY, TEXT_SECONDARY, dashed=True)
    ax.annotate(
        "", xy=(xs[1] + box_w / 2, y_top), xytext=(xs[1] + box_w / 2, y_bot + box_h),
        arrowprops=dict(arrowstyle="<->", color=GREY, linestyle="dashed", lw=1.2),
    )
    ax.annotate(
        "", xy=(xs[2] + box_w / 2, y_top), xytext=(xs[2] + box_w / 2, y_bot + box_h),
        arrowprops=dict(arrowstyle="<->", color=GREY, linestyle="dashed", lw=1.2),
    )

    ax.text(
        start_x, y_bot - 0.07,
        "Target architecture (Section 3.2) -- NOT implemented; not part of any claim in Sections 6-8",
        fontsize=11, color=TEXT_SECONDARY, style="italic",
    )

    fig.tight_layout()
    fig.savefig(OUT_PATH)
    plt.close(fig)
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
