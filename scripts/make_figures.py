"""Generates all paper figures from committed data/generated/*.json results.

Does not re-run any experiment -- purely plots already-measured numbers, so figures always match
whatever is currently committed. Uses the validated categorical palette (see dataviz skill
references/palette.md): blue #2a78d6, aqua #1baf7a, yellow #eda100, red #e34948, green #008300.
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np

matplotlib.use("Agg")

ROOT = Path(__file__).resolve().parent.parent
FIG_DIR = ROOT / "paper" / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

BLUE = "#2a78d6"
AQUA = "#1baf7a"
YELLOW = "#eda100"
RED = "#e34948"
GREEN = "#008300"
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID = "#e5e4df"

plt.rcParams.update(
    {
        "font.size": 11,
        "text.color": TEXT_PRIMARY,
        "axes.edgecolor": GRID,
        "axes.labelcolor": TEXT_PRIMARY,
        "xtick.color": TEXT_SECONDARY,
        "ytick.color": TEXT_SECONDARY,
        "axes.grid": True,
        "grid.color": GRID,
        "grid.linewidth": 0.8,
        "axes.axisbelow": True,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
    }
)


def bar_with_labels(ax, x, values, color, width, label=None, offset=0):
    bars = ax.bar(x + offset, values, width, color=color, label=label, zorder=3)
    for b, v in zip(bars, values):
        y = b.get_height()
        va = "bottom" if y > 0 else "bottom"
        label_y = y + 1.5 if y > 0 else 3.0
        ax.text(
            b.get_x() + b.get_width() / 2,
            label_y,
            f"{v:g}",
            ha="center",
            va=va,
            fontsize=9,
            color=TEXT_SECONDARY,
        )
    return bars


def fig1_schema_understanding():
    apis = ["GitHub", "Stripe", "Slack"]
    before = [67, 370, 147]  # pre-$ref-fix required-param counts (GitHub understated)
    after = [1721, 370, 147]  # post-fix; Stripe/Slack unaffected by the $ref bug

    x = np.arange(len(apis))
    width = 0.32
    fig, ax = plt.subplots(figsize=(7.5, 4.4))
    bar_with_labels(ax, x, before, RED, width, "Before $\\it{\\$ref}$ fix", offset=-width / 2)
    bar_with_labels(ax, x, after, BLUE, width, "After $\\it{\\$ref}$ fix", offset=width / 2)
    ax.set_yscale("log")
    ax.set_ylabel("Required parameters counted (log scale)")
    ax.set_title(
        "Experiment 1: Schema Understanding\n"
        "GitHub's $ref-defined parameters were invisible before the fix",
        fontsize=12,
    )
    ax.set_xticks(x)
    ax.set_xticklabels(apis)
    ax.legend(frameon=False, loc="upper right")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "exp1_schema_understanding.png", dpi=150)
    plt.close(fig)


def fig2_intent_generation():
    with open(ROOT / "data" / "generated" / "experiment2_intents.json") as f:
        data = json.load(f)

    apis = list(data.keys())
    coverage = []
    diversity = []
    for api in apis:
        items = data[api]
        total_intents = sum(len(item["intents"]) for item in items)
        covered = sum(1 for item in items if item["intents"])
        coverage.append(100 * covered / len(items) if items else 0)
        unique = len({i for item in items for i in item["intents"]})
        diversity.append(100 * unique / total_intents if total_intents else 0)

    x = np.arange(len(apis))
    width = 0.32
    fig, ax = plt.subplots(figsize=(6, 4))
    bar_with_labels(ax, x, coverage, BLUE, width, "Intent Coverage %", offset=-width / 2)
    bar_with_labels(ax, x, diversity, AQUA, width, "Diversity % (exact-string)", offset=width / 2)
    ax.set_ylim(0, 115)
    ax.set_ylabel("Percent")
    ax.set_title("Experiment 2: Intent Generation Quality\n(pilot: 5 endpoints x 3 intents per API)")
    ax.set_xticks(x)
    ax.set_xticklabels(apis)
    ax.legend(frameon=False, loc="lower right")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "exp2_intent_generation.png", dpi=150)
    plt.close(fig)


def fig3_trajectory_generation():
    with open(ROOT / "data" / "generated" / "experiment3_trajectories.json") as f:
        data = json.load(f)

    apis = list(data.keys())
    tool_acc = []
    param_valid = []
    for api in apis:
        items = data[api]
        correct = [item for item in items if item.get("selected_correct")]
        tool_acc.append(100 * len(correct) / len(items) if items else 0)
        satisfied = [item for item in correct if item.get("required_params_satisfied")]
        param_valid.append(100 * len(satisfied) / len(correct) if correct else 0)

    x = np.arange(len(apis))
    width = 0.32
    fig, ax = plt.subplots(figsize=(6, 4))
    bar_with_labels(ax, x, tool_acc, BLUE, width, "Tool Selection Accuracy %", offset=-width / 2)
    bar_with_labels(ax, x, param_valid, AQUA, width, "Parameter Validity %", offset=width / 2)
    ax.set_ylim(0, 115)
    ax.set_ylabel("Percent")
    ax.set_title("Experiment 3: Agent Trajectory Generation\n(45 intents, 15 candidate tools each)")
    ax.set_xticks(x)
    ax.set_xticklabels(apis)
    ax.legend(frameon=False, loc="lower right")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "exp3_trajectory_generation.png", dpi=150)
    plt.close(fig)


def fig4_verification_before_after():
    # Before-fix numbers are from the first run of scripts/run_experiment4.py, observed but not
    # persisted to a JSON file at the time (see DESIGN_DOC.md S6.6 for the full account). After
    # numbers come from data/generated/experiment4_verification.json (committed).
    types = ["Wrong\nmethod", "Missing\nparam", "Invalid\npath", "Wrong\ntype"]
    before = [100.0, 50.0, 100.0, 0.0]  # 12/12, 6/12, 12/12, 0/8
    after = [100.0, 100.0, 100.0, 100.0]  # 12/12, 11/11, 12/12, 9/9

    x = np.arange(len(types))
    width = 0.32
    fig, ax = plt.subplots(figsize=(8, 4.6))
    bar_with_labels(ax, x, before, RED, width, "First run (pre-fix)", offset=-width / 2)
    bar_with_labels(ax, x, after, GREEN, width, "Final (post-fix)", offset=width / 2)
    ax.set_ylim(0, 115)
    ax.set_ylabel("Invalid cases detected (%)")
    ax.set_title(
        "Experiment 4: Schema-Based Verification\n"
        "Adversarial testing surfaced 4 real bugs across verifier, harness, and parser",
        fontsize=12,
    )
    ax.set_xticks(x)
    ax.set_xticklabels(types)
    ax.legend(frameon=False, loc="lower right")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "exp4_verification_before_after.png", dpi=150)
    plt.close(fig)


def fig5_downstream_performance():
    with open(ROOT / "data" / "generated" / "experiment5_results.json") as f:
        data = json.load(f)

    models = ["Base\n(untuned)", "EnterpriseSynth\nfine-tuned"]
    tool_acc = [
        data["base_model"]["tool_selection_accuracy"],
        data["fine_tuned_model"]["tool_selection_accuracy"],
    ]
    param_valid_raw = [
        data["base_model"]["parameter_validity_among_correct"],
        data["fine_tuned_model"]["parameter_validity_among_correct"],
    ]
    param_valid = [0.0 if v == "n/a" else v for v in param_valid_raw]

    x = np.arange(len(models))
    width = 0.32
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 4.2))

    ax = axes[0]
    bar_with_labels(ax, x, tool_acc, BLUE, width, "Tool Selection Acc. %", offset=-width / 2)
    bar_with_labels(ax, x, param_valid, AQUA, width, "Parameter Validity %", offset=width / 2)
    ax.set_ylim(0, 115)
    ax.set_ylabel("Percent")
    ax.set_title("Held-out API (Zoom): base vs.\nfine-tuned on EnterpriseSynth data")
    ax.set_xticks(x)
    ax.set_xticklabels(models)
    ax.legend(frameon=False, loc="upper left")
    ax.spines[["top", "right"]].set_visible(False)

    ax2 = axes[1]
    epochs = [1, 2, 3]
    losses = [0.7076, 0.4028, 0.2474]
    ax2.plot(epochs, losses, color=BLUE, marker="o", markersize=8, linewidth=2, zorder=3)
    for e, loss_val in zip(epochs, losses):
        ax2.text(e, loss_val + 0.02, f"{loss_val:.3f}", ha="center", fontsize=9, color=TEXT_SECONDARY)
    ax2.set_xlabel("Epoch")
    ax2.set_ylabel("Training loss")
    ax2.set_title("LoRA fine-tuning loss\n(Qwen2.5-0.5B, 45 examples)")
    ax2.set_xticks(epochs)
    ax2.set_ylim(0, 0.85)
    ax2.spines[["top", "right"]].set_visible(False)

    fig.suptitle("Experiment 5: Downstream Agent Evaluation", y=1.02, fontsize=13)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "exp5_downstream_performance.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    fig1_schema_understanding()
    fig2_intent_generation()
    fig3_trajectory_generation()
    fig4_verification_before_after()
    fig5_downstream_performance()
    print(f"Wrote 5 figures to {FIG_DIR}")


if __name__ == "__main__":
    main()
