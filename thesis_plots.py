import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/matplotlib-cache")
Path(os.environ["MPLCONFIGDIR"]).mkdir(parents=True, exist_ok=True)

from matplotlib import use

use("Agg")

import matplotlib.pyplot as plt
import pandas as pd


CSV_PATH = Path("database/benchmarks/benchmark_results.csv")
OUT_DIR = Path("database/benchmarks/plots")
THESIS_COMPANIES = [
    "Apple",
    "Samsung",
    "Nvidia",
    "AMD",
    "Intel",
    "Microsoft",
    "Tesla",
    "TSMC",
    "ASML",
    "Foxconn",
]
MODE_ORDER = ["llm", "rag"]
MODE_LABELS = {"llm": "LLM", "rag": "RAG"}


plt.style.use("seaborn-v0_8-whitegrid")
plt.rcParams.update(
    {
        "figure.dpi": 300,
        "savefig.dpi": 300,
        "font.size": 11,
        "axes.titlesize": 15,
        "axes.labelsize": 12,
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
        "legend.fontsize": 10,
    }
)


def load_data() -> pd.DataFrame:
    df = pd.read_csv(CSV_PATH)
    if "evaluation_status" not in df.columns:
        raise ValueError("benchmark_results.csv is missing the evaluation_status column")
    numeric_cols = [
        "accuracy_score",
        "precision",
        "recall",
        "retrieval_grounding_score",
        "coverage_score",
        "tier_discovery_effectiveness",
        "runtime_seconds",
        "token_usage",
        "estimated_api_cost",
        "estimated_energy_consumption",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def success_only(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["evaluation_status"] == "success"].copy()


def ensure_output_dir() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)


def format_mode_data(df: pd.DataFrame, metric: str) -> pd.Series:
    series = df.groupby("mode")[metric].mean().reindex(MODE_ORDER)
    missing = series[series.isna()].index.tolist()
    if missing:
        raise ValueError(f"Missing data for modes: {missing} in metric {metric}")
    return series


def add_value_labels(ax, values, fmt="{:,.2f}", offset=0.01):
    ymin, ymax = ax.get_ylim()
    span = ymax - ymin if ymax > ymin else 1.0
    for bar, value in zip(ax.patches, values):
        height = bar.get_height()
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            height + span * offset,
            fmt.format(value),
            ha="center",
            va="bottom",
            fontsize=9,
        )


def plot_grouped_bars(
    data: pd.DataFrame,
    metrics,
    title: str,
    ylabel: str,
    outfile: str,
    metric_labels=None,
    value_fmt="{:,.2f}",
    figsize=(11, 6),
):
    metric_labels = metric_labels or metrics
    fig, ax = plt.subplots(figsize=figsize)
    x = range(len(metrics))
    width = 0.35

    llm_values = [data.loc[m, "llm"] for m in metrics]
    rag_values = [data.loc[m, "rag"] for m in metrics]

    bars_llm = ax.bar([i - width / 2 for i in x], llm_values, width, label="LLM")
    bars_rag = ax.bar([i + width / 2 for i in x], rag_values, width, label="RAG")

    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.set_xticks(list(x))
    ax.set_xticklabels(metric_labels, rotation=25, ha="right")
    ax.legend(frameon=False, ncol=2, loc="upper center", bbox_to_anchor=(0.5, 1.12))

    all_values = llm_values + rag_values
    max_value = max(all_values) if all_values else 0
    ax.set_ylim(0, max_value * 1.18 if max_value > 0 else 1)

    for bars, values in ((bars_llm, llm_values), (bars_rag, rag_values)):
        for bar, value in zip(bars, values):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + (max_value * 0.02 if max_value > 0 else 0.01),
                value_fmt.format(value),
                ha="center",
                va="bottom",
                fontsize=9,
            )

    fig.subplots_adjust(left=0.16, right=0.97, top=0.86, bottom=0.18)
    path = OUT_DIR / outfile
    fig.savefig(path, dpi=300)
    plt.close(fig)
    return path


def plot_single_metric(
    data: pd.Series,
    title: str,
    ylabel: str,
    outfile: str,
    value_fmt="{:,.2f}",
    figsize=(8.5, 6.2),
):
    fig, ax = plt.subplots(figsize=figsize)
    colors = ["#4C78A8", "#F58518"]
    bars = ax.bar(
        [MODE_LABELS[m] for m in MODE_ORDER],
        [data[m] for m in MODE_ORDER],
        color=colors,
        width=0.55,
    )
    ax.set_title(title, pad=12)
    ax.set_ylabel(ylabel, labelpad=10)
    ax.set_ylim(0, max(data.max() * 1.22, 1e-9))

    for bar, value in zip(bars, [data[m] for m in MODE_ORDER]):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + max(data.max() * 0.015, 0.01),
            value_fmt.format(value),
            ha="center",
            va="bottom",
            fontsize=9,
        )

    fig.subplots_adjust(left=0.16, right=0.97, top=0.86, bottom=0.18)
    path = OUT_DIR / outfile
    fig.savefig(path, dpi=300)
    plt.close(fig)
    return path


def plot_company_metric(
    df: pd.DataFrame,
    metric: str,
    title: str,
    ylabel: str,
    outfile: str,
    companies,
    value_fmt="{:,.2f}",
    figsize=(13, 6.5),
):
    company_order = list(companies)
    pivot = (
        df[df["company"].isin(company_order)]
        .pivot_table(index="company", columns="mode", values=metric, aggfunc="mean")
        .reindex(company_order)
        .reindex(columns=MODE_ORDER)
    )
    if pivot.isna().any().any():
        missing = pivot[pivot.isna().any(axis=1)].index.tolist()
        raise ValueError(f"Missing data for companies in {metric}: {missing}")

    fig, ax = plt.subplots(figsize=figsize)
    x = range(len(company_order))
    width = 0.35
    llm_values = pivot["llm"].tolist()
    rag_values = pivot["rag"].tolist()

    bars_llm = ax.bar([i - width / 2 for i in x], llm_values, width, label="LLM")
    bars_rag = ax.bar([i + width / 2 for i in x], rag_values, width, label="RAG")

    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.set_xticks(list(x))
    ax.set_xticklabels(company_order, rotation=30, ha="right")
    ax.legend(frameon=False, ncol=2, loc="upper center", bbox_to_anchor=(0.5, 1.12))

    max_value = max(llm_values + rag_values)
    ax.set_ylim(0, max_value * 1.18 if max_value > 0 else 1)

    for bars, values in ((bars_llm, llm_values), (bars_rag, rag_values)):
        for bar, value in zip(bars, values):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + (max_value * 0.02 if max_value > 0 else 0.01),
                value_fmt.format(value),
                ha="center",
                va="bottom",
                fontsize=8,
            )

    fig.tight_layout(pad=1.5)
    path = OUT_DIR / outfile
    fig.savefig(path, dpi=300)
    plt.close(fig)
    return path


def plot_evaluation_classification(df: pd.DataFrame, outfile: str):
    company_status = df.groupby("company")["evaluation_status"].first()
    counts = company_status.value_counts().reindex(
        ["success", "insufficient_public_supply_chain_data", "system_failure"],
        fill_value=0,
    )
    labels = [
        "Successful Evaluations",
        "Insufficient Public Data Cases",
        "System Failures",
    ]
    values = [int(counts["success"]), int(counts["insufficient_public_supply_chain_data"]), int(counts["system_failure"])]

    fig, ax = plt.subplots(figsize=(7.5, 7.5))
    colors = ["#4C78A8", "#F58518", "#E45756"]
    wedges, texts, autotexts = ax.pie(
        values,
        labels=labels,
        autopct=lambda pct: f"{pct:.1f}%" if pct > 0 else "",
        startangle=90,
        colors=colors,
        textprops={"fontsize": 10},
    )
    for autotext in autotexts:
        autotext.set_color("white")
        autotext.set_fontsize(10)
    ax.set_title("Evaluation Classification")
    ax.axis("equal")
    fig.tight_layout(pad=1.5)
    path = OUT_DIR / outfile
    fig.savefig(path, dpi=300)
    plt.close(fig)
    return path


def main():
    ensure_output_dir()
    df = load_data()
    eval_df = success_only(df)

    generated = []

    quality_metrics = [
        "accuracy_score",
        "precision",
        "recall",
        "retrieval_grounding_score",
        "coverage_score",
        "tier_discovery_effectiveness",
    ]
    quality_labels = [
        "F1 Score",
        "Precision",
        "Recall",
        "Retrieval Grounding Score",
        "Coverage Score",
        "Tier Discovery Effectiveness",
    ]
    quality_data = eval_df.groupby("mode")[quality_metrics].mean().reindex(MODE_ORDER).T
    generated.append(
        plot_grouped_bars(
            quality_data,
            quality_metrics,
            "LLM vs RAG: Thesis Quality Metrics",
            "Score",
            "quality_metrics_comparison.png",
            metric_labels=quality_labels,
            value_fmt="{:,.2f}",
            figsize=(12.5, 6.5),
        )
    )

    generated.append(
        plot_single_metric(
            format_mode_data(eval_df, "runtime_seconds"),
            "LLM vs RAG: Runtime",
            "Runtime (seconds)",
            "runtime_comparison.png",
            value_fmt="{:,.2f}",
        )
    )
    generated.append(
        plot_single_metric(
            format_mode_data(eval_df, "token_usage"),
            "LLM vs RAG: Token Usage",
            "Token Usage",
            "token_usage_comparison.png",
            value_fmt="{:,.0f}",
        )
    )
    generated.append(
        plot_single_metric(
            format_mode_data(eval_df, "estimated_api_cost"),
            "LLM vs RAG: Estimated API Cost",
            "Estimated API Cost (USD)",
            "api_cost_comparison.png",
            value_fmt="${:,.4f}",
        )
    )
    generated.append(
        plot_single_metric(
            format_mode_data(eval_df, "estimated_energy_consumption"),
            "LLM vs RAG: Estimated Energy Consumption",
            "Estimated Energy Consumption (kWh)",
            "energy_consumption_comparison.png",
            value_fmt="{:,.6f}",
        )
    )
    generated.append(
        plot_company_metric(
            eval_df,
            "accuracy_score",
            "Company-wise F1 Score: LLM vs RAG",
            "F1 Score",
            "company_f1_comparison.png",
            THESIS_COMPANIES,
            value_fmt="{:,.2f}",
            figsize=(13.5, 6.8),
        )
    )
    generated.append(
        plot_company_metric(
            eval_df,
            "recall",
            "Company-wise Recall: LLM vs RAG",
            "Recall",
            "company_recall_comparison.png",
            THESIS_COMPANIES,
            value_fmt="{:,.2f}",
            figsize=(13.5, 6.8),
        )
    )
    generated.append(
        plot_evaluation_classification(df, "evaluation_classification.png")
    )

    print("Output directory:", OUT_DIR)
    print("Generated files:")
    for path in generated:
        print(f"- {path}")


if __name__ == "__main__":
    main()
