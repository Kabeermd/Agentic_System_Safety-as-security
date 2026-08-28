#!/usr/bin/env python
"""
pcer/visualize.py — PCER results visualiser (seaborn-styled).

Same row contract, CLI, and modes as before (compare / profile / aggregate /
bars / table), restyled with a cohesive design system matching the RedCode
figures: consistent palette, clean typography, minimalist grids, clear insights.

ROW CONTRACT (unchanged — what pcer/judge.py writes):
    {"instance_id","scores":{5 dims},"condition","resolved","failure_classes"}
A dimension null in any plotted row is dropped automatically (so Safety
Compliance disappears cleanly on baseline-only comparisons).

MODES:
    compare   side-by-side radar, one panel per condition (poster view)
    profile   single overlaid radar, colour by condition
    aggregate mean polygon per condition (+ optional min-max band)
    bars      grouped bars, mean per dimension per condition
    table     arch-vs-baseline score table -> CSV + LaTeX + rendered image

USAGE:
    python pcer/visualize.py --mode compare  pcer/scores/*arch*.jsonl pcer/scores/*baseline*.jsonl
    python pcer/visualize.py --mode bars     pcer/scores/*.jsonl
    python pcer/visualize.py --mode aggregate --band pcer/scores/*.jsonl
    python pcer/visualize.py --mode table    pcer/scores/*.jsonl
"""

import os
import sys
import glob
import json
import argparse
from collections import defaultdict, OrderedDict

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
import seaborn as sns

 
# Design system (shared with RedCode figures)

INK, MUTED, FAINT = "#22223B", "#7A7A93", "#ECECF2"
# condition palette: arch = indigo (instrumented), baseline = coral (bare)
C_ARCH, C_BASELINE = "#4A5FC1", "#D9534F"
# per-instance palette (calm, distinct, colourblind-aware)
PALETTE = ["#3C9A7B", "#4A5FC1", "#D9534F", "#E0A030", "#7E5BA6",
           "#3B8EA5", "#C65D7B", "#6B8E23", "#5A5A6E"]
COND_COLORS = {"arch": C_ARCH, "baseline": C_BASELINE}

FONT_STACK = ["Calibri", "Times New Roman", "Georgia", "DejaVu Sans"]
MAX_OVERLAY = 8

sns.set_theme(style="whitegrid", context="talk")
plt.rcParams.update({
    "font.family": FONT_STACK, "svg.fonttype": "none",
    "figure.facecolor": "white", "axes.facecolor": "white",
    "axes.edgecolor": FAINT, "grid.color": FAINT,
    "text.color": INK, "axes.labelcolor": INK,
    "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.spines.top": False, "axes.spines.right": False,
})

SCHEMAS = {
    "pcer": {"scale_max": 5, "dims": [
        ("reasoning_coherence",     "Reasoning\nCoherence"),
        ("tool_efficiency",         "Tool\nEfficiency"),
        ("safety_compliance",       "Safety\nCompliance"),
        ("recovery_rate",           "Recovery\nRate"),
        ("verification_completion", "Verification\nCompletion"),
    ]},
}
SHORT = {"reasoning_coherence": "RC", "tool_efficiency": "TE",
         "safety_compliance": "SC", "recovery_rate": "RR",
         "verification_completion": "VC"}


def _suptitle(fig, title, subtitle=None, y=1.02, x=0.5):
    fig.suptitle(title, fontsize=16, fontweight="bold", color=INK, x=x, y=y)
    if subtitle:
        fig.text(x, y - 0.06, subtitle, fontsize=10.5, color=MUTED, ha="center")




def _expand_inputs(inputs):
    paths = []
    for item in inputs:
        if os.path.isdir(item):
            paths.extend(sorted(glob.glob(os.path.join(item, "*.jsonl"))))
        else:
            expanded = sorted(glob.glob(item))
            paths.extend(expanded if expanded else [item])
    seen, out = set(), []
    for p in paths:
        if p not in seen and os.path.exists(p):
            seen.add(p); out.append(p)
    return out


def repo_of(iid):
    return iid.split("__")[0] if "__" in str(iid) else str(iid)


def load_rows(inputs):
    rows, files = [], _expand_inputs(inputs)
    if not files:
        sys.exit(f"[viz] no score files matched: {inputs}")
    for path in files:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not d.get("scores"):
                    continue
                iid = d.get("instance_id", "?")
                rows.append({"instance_id": iid, "repo": repo_of(iid),
                             "condition": d.get("condition") or "unlabelled",
                             "resolved": d.get("resolved"),
                             "failure_classes": d.get("failure_classes", []),
                             "scores": d["scores"], "source": os.path.basename(path)})
    print(f"[viz] loaded {len(rows)} rows from {len(files)} file(s)")
    return rows


def active_dims(rows, schema):
    active = []
    for k, label in schema["dims"]:
        vals = [r["scores"].get(k) for r in rows]
        if vals and all(v is not None for v in vals):
            active.append((k, label))
    dropped = [k for k, _ in schema["dims"] if k not in [a for a, _ in active]]
    if dropped:
        print(f"[viz] dropping dims null in some/all rows: {dropped}")
    if len(active) < 3:
        sys.exit(f"[viz] only {len(active)} usable dims — need >=3 for radar; try --mode bars.")
    return active



# Radar primitives

def _radar_setup(ax, labels, scale_max):
    N = len(labels)
    angles = np.linspace(0, 2*np.pi, N, endpoint=False).tolist(); angles += angles[:1]
    ax.set_theta_offset(np.pi/2); ax.set_theta_direction(-1)
    ax.set_ylim(0, scale_max)
    ax.set_yticks(list(range(1, scale_max+1)))
    ax.set_yticklabels([str(t) for t in range(1, scale_max+1)], fontsize=9, color=MUTED)
    ax.set_rlabel_position(180/N)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, fontsize=11, fontweight="bold", color=INK)
    ax.tick_params(axis="x", pad=14)
    ax.spines["polar"].set_color(FAINT)
    ax.grid(color=FAINT, linewidth=1.1)
    return angles


def _plot_series(ax, angles, vals, color, resolved=None, label=None, lw=2.6):
    v = list(vals) + [vals[0]]
    ls = "-" if (resolved is None or resolved) else (0, (5, 3))
    ax.plot(angles, v, color=color, linewidth=lw, linestyle=ls, zorder=3, label=label)
    ax.fill(angles, v, color=color, alpha=0.12, zorder=2)
    ax.scatter(angles[:-1], vals, color=color, s=44, zorder=4,
               edgecolors="white", linewidths=1.1)


def _series_vals(row, dims):
    return [row["scores"][k] for k, _ in dims]


def _conditions(rows):
    out = OrderedDict()
    for r in rows:
        out.setdefault(r["condition"], True)
    # canonical order arch before baseline if present
    conds = list(out.keys())
    conds.sort(key=lambda c: (c != "arch", c))
    return conds



# compare — side-by-side radars
 
def mode_compare(rows, schema, args):
    dims = active_dims(rows, schema)
    labels = [l for _, l in dims]
    conds = _conditions(rows)
    n = len(conds)
    fig, axes = plt.subplots(1, n, figsize=(7.2*n, 7.0),
                             subplot_kw=dict(polar=True), squeeze=False)
    axes = axes[0]
    all_iids = sorted({r["instance_id"] for r in rows})
    cmap = {iid: PALETTE[i % len(PALETTE)] for i, iid in enumerate(all_iids)}

    for ax, cond in zip(axes, conds):
        crows = [r for r in rows if r["condition"] == cond]
        angles = _radar_setup(ax, labels, schema["scale_max"])
        for r in sorted(crows, key=lambda x: x["instance_id"]):
            _plot_series(ax, angles, _series_vals(r, dims), cmap[r["instance_id"]],
                         resolved=r["resolved"])
        has_res = any(r["resolved"] is not None for r in crows)
        n_res = sum(1 for r in crows if r["resolved"])
        sub = f"{n_res}/{len(crows)} resolved" if has_res else f"{len(crows)} instance(s)"
        cond_col = COND_COLORS.get(cond, INK)
        ax.set_title(cond.capitalize(), fontsize=15, fontweight="bold",
                     color=cond_col, pad=24)
        ax.text(0.5, -0.16, sub, transform=ax.transAxes, ha="center",
                fontsize=10.5, color=MUTED)

    handles = [Line2D([0], [0], color=cmap[i], lw=3, marker="o", markersize=7,
                      markeredgecolor="white", label=i.split("__")[-1]) for i in all_iids]
    if any(r["resolved"] is False for r in rows):
        handles.append(Line2D([0], [0], color=MUTED, lw=2.2, linestyle=(0, (5, 3)),
                              label="dashed = not resolved"))
    fig.legend(handles=handles, loc="lower center", ncol=min(len(handles), 4),
               frameon=False, fontsize=10, bbox_to_anchor=(0.5, -0.02))
    _suptitle(fig, args.title or "PCER process profiles by condition",
              "Each polygon is one task's five-dimension process quality (1\u20135)")
    plt.subplots_adjust(top=0.82, bottom=0.16, wspace=0.55)
    return fig


def mode_profile(rows, schema, args):
    dims = active_dims(rows, schema)
    labels = [l for _, l in dims]
    conds = _conditions(rows)
    ccolor = {c: COND_COLORS.get(c, PALETTE[i]) for i, c in enumerate(conds)}
    fig, ax = plt.subplots(figsize=(8.4, 8.4), subplot_kw=dict(polar=True))
    angles = _radar_setup(ax, labels, schema["scale_max"])
    for r in sorted(rows, key=lambda x: (x["condition"], x["instance_id"])):
        _plot_series(ax, angles, _series_vals(r, dims), ccolor[r["condition"]],
                     resolved=r["resolved"])
    handles = [Line2D([0], [0], color=ccolor[c], lw=3, marker="o", markersize=7,
                      markeredgecolor="white", label=c.capitalize()) for c in conds]
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.07),
              frameon=False, ncol=len(conds), fontsize=11)
    _suptitle(fig, args.title or "PCER process profiles", y=0.99)
    plt.subplots_adjust(top=0.86, bottom=0.14)
    return fig


def _means(rows, dims):
    return [float(np.mean([r["scores"][k] for r in rows])) for k, _ in dims]


def mode_aggregate(rows, schema, args):
    dims = active_dims(rows, schema)
    labels = [l for _, l in dims]
    conds = _conditions(rows)
    ccolor = {c: COND_COLORS.get(c, PALETTE[i]) for i, c in enumerate(conds)}
    fig, ax = plt.subplots(figsize=(8.6, 8.6), subplot_kw=dict(polar=True))
    angles = _radar_setup(ax, labels, schema["scale_max"])
    for c in conds:
        crows = [r for r in rows if r["condition"] == c]
        means = _means(crows, dims)
        _plot_series(ax, angles, means, ccolor[c], label=c.capitalize(), lw=3.0)
        if len(crows) > 1 and args.band:
            mat = np.array([[r["scores"][k] for k, _ in dims] for r in crows])
            lo = mat.min(axis=0).tolist() + [mat.min(axis=0)[0]]
            hi = mat.max(axis=0).tolist() + [mat.max(axis=0)[0]]
            ax.fill_between(angles, lo, hi, color=ccolor[c], alpha=0.08, zorder=1)
    handles = [Line2D([0], [0], color=ccolor[c], lw=3.2, marker="o", markersize=7,
               markeredgecolor="white",
               label=f"{c.capitalize()}  (n={sum(1 for r in rows if r['condition']==c)})")
               for c in conds]
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.07),
              frameon=False, ncol=len(conds), fontsize=11)
    _suptitle(fig, args.title or "PCER — mean process profile per condition", y=0.99)
    plt.subplots_adjust(top=0.86, bottom=0.14)
    return fig


def mode_bars(rows, schema, args):
    dims = active_dims(rows, schema)
    labels = [l.replace("\n", " ") for _, l in dims]
    conds = _conditions(rows)
    ccolor = {c: COND_COLORS.get(c, PALETTE[i]) for i, c in enumerate(conds)}
    means = {c: _means([r for r in rows if r["condition"] == c], dims) for c in conds}
    x = np.arange(len(dims)); w = 0.8 / max(len(conds), 1)
    fig, ax = plt.subplots(figsize=(1.7*len(dims)+3, 6))
    for i, c in enumerate(conds):
        bars = ax.bar(x + i*w - 0.4 + w/2, means[c], width=w*0.9,
                      color=ccolor[c], edgecolor="white", linewidth=1.5,
                      label=f"{c.capitalize()} (n={sum(1 for r in rows if r['condition']==c)})")
        for rect, v in zip(bars, means[c]):
            ax.text(rect.get_x()+rect.get_width()/2, v+0.08, f"{v:.1f}",
                    ha="center", va="bottom", fontsize=10, fontweight="bold")
    ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=11)
    ax.set_ylim(0, schema["scale_max"]+0.4)
    ax.set_ylabel("Mean score (1\u20135)", fontsize=12)
    ax.grid(axis="x", visible=False); sns.despine(ax=ax)
    ax.legend(frameon=False, fontsize=11, loc="upper right")
    _suptitle(fig, args.title or "PCER — mean score per dimension",
              "Higher is better; Safety Compliance present only where the CRM annotated")
    plt.tight_layout(rect=(0, 0, 1, 0.90))
    return fig


 
# table (CSV + LaTeX + rendered) — logic unchanged, styling refreshed

def _table_matrix(rows, schema):
    dim_keys = [k for k, _ in schema["dims"]]
    conds = _conditions(rows)
    insts = sorted({r["instance_id"] for r in rows})
    table = []
    for inst in insts:
        for cond in conds:
            match = [r for r in rows if r["instance_id"] == inst and r["condition"] == cond]
            if not match:
                continue
            r = match[0]
            row = {"task": inst.split("__")[-1], "condition": cond}
            for k in dim_keys:
                row[k] = r["scores"].get(k)
            row["resolved"] = r["resolved"]
            table.append(row)
    for cond in conds:
        crows = [r for r in rows if r["condition"] == cond]
        row = {"task": "mean", "condition": cond}
        for k in dim_keys:
            vals = [r["scores"].get(k) for r in crows if r["scores"].get(k) is not None]
            row[k] = round(float(np.mean(vals)), 2) if vals else None
        has_res = any(r["resolved"] is not None for r in crows)
        row["resolved"] = (f"{sum(1 for r in crows if r['resolved'])}/{len(crows)}"
                           if has_res else None)
        table.append(row)
    return dim_keys, table


def _fmt(v):
    if v is None: return "\u2013"
    if v is True: return "\u2713"
    if v is False: return "\u2717"
    return f"{v:g}" if isinstance(v, float) else str(v)


def _write_csv(dim_keys, table, path):
    import csv
    cols = ["task", "condition"] + dim_keys + ["resolved"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["task", "condition"] + [SHORT.get(k, k) for k in dim_keys] + ["resolved"])
        for r in table:
            w.writerow([r.get(c) if r.get(c) is not None else "" for c in cols])
    print(f"[viz] wrote {path}")


def _write_latex(dim_keys, table, path, caption):
    heads = " & ".join(["Task", "Cond."] + [SHORT.get(k, k) for k in dim_keys] + ["Res."]) # type: ignore
    lines = [r"\begin{table}[t]", r"\centering", r"\caption{"+caption+r"}",
             r"\label{tab:pcer}", r"\begin{tabular}{ll"+"c"*len(dim_keys)+"c}",
             r"\toprule", heads+r" \\", r"\midrule"]
    for i, r in enumerate(table):
        if r["task"] == "mean" and (i == 0 or table[i-1]["task"] != "mean"):
            lines.append(r"\midrule")
        cells = [r["task"], r["condition"]] + [_fmt(r.get(k)) for k in dim_keys] + [_fmt(r.get("resolved"))]
        cells = [c.replace("\u2713", r"\checkmark").replace("\u2717", r"$\times$")
                 .replace("\u2013", "--") for c in cells]
        lines.append(" & ".join(cells) + r" \\")
    lines += [r"\bottomrule", r"\end{tabular}",
              r"\\[2pt] \footnotesize RC Reasoning Coherence, TE Tool Efficiency, "
              r"SC Safety Compliance, RR Recovery Rate, VC Verification Completion. "
              r"1--5, higher better; -- = not available.", r"\end{table}"]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"[viz] wrote {path}")


def mode_table(rows, schema, args):
    dim_keys, table = _table_matrix(rows, schema)
    stem = args.stem
    _write_csv(dim_keys, table, stem + ".csv")
    _write_latex(dim_keys, table, stem + ".tex",
                 args.title or "PCER scores per task and condition.")
    col_labels = ["Task", "Cond."] + [SHORT.get(k, k) for k in dim_keys] + ["Res."]
    cell_text, row_is_mean = [], []
    for r in table:
        cell_text.append([r["task"], r["condition"]] +
                         [_fmt(r.get(k)) for k in dim_keys] + [_fmt(r.get("resolved"))])
        row_is_mean.append(r["task"] == "mean")
    fig, ax = plt.subplots(figsize=(1.2*len(col_labels)+1.5, 0.55*len(table)+1.6))
    ax.axis("off")
    tbl = ax.table(cellText=cell_text, colLabels=col_labels, loc="center", cellLoc="center") # type: ignore
    tbl.auto_set_font_size(False); tbl.set_fontsize(11); tbl.scale(1, 1.55)
    for (r_i, c_i), cell in tbl.get_celld().items():
        cell.set_edgecolor(FAINT)
        if r_i == 0:
            cell.set_facecolor(C_ARCH); cell.set_text_props(color="white", fontweight="bold")
        else:
            is_mean = row_is_mean[r_i-1] if r_i-1 < len(row_is_mean) else False
            cell.set_facecolor("#F0F2FA" if is_mean else "white")
            if is_mean:
                cell.set_text_props(fontweight="bold")
    ax.set_title(args.title or "PCER scores \u2014 arch vs baseline",
                 fontsize=15, fontweight="bold", color=INK, pad=14)
    fig.text(0.5, 0.02,
             "RC Reasoning Coherence · TE Tool Efficiency · SC Safety Compliance · "
             "RR Recovery Rate · VC Verification Completion   (1\u20135; \u2013 = n/a)",
             ha="center", fontsize=8.5, color=MUTED)
    plt.tight_layout(rect=(0, 0.04, 1, 1))
    return fig


MODES = {"compare": mode_compare, "profile": mode_profile,
         "aggregate": mode_aggregate, "bars": mode_bars, "table": mode_table}


def main():
    ap = argparse.ArgumentParser(description="Visualise PCER score JSONL files.")
    ap.add_argument("inputs", nargs="+")
    ap.add_argument("--mode", choices=list(MODES), default="compare")
    ap.add_argument("--schema", choices=list(SCHEMAS), default="pcer")
    ap.add_argument("--group-by", choices=["instance", "repo"], default="instance")
    ap.add_argument("--band", action="store_true")
    ap.add_argument("--force-overlay", action="store_true")
    ap.add_argument("--title", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--formats", default="svg,png")
    ap.add_argument("--dpi", type=int, default=300)
    args = ap.parse_args()

    rows = load_rows(args.inputs)
    if not rows:
        sys.exit("[viz] nothing to plot.")

    if args.group_by == "repo" and args.mode in ("aggregate", "bars"):
        schema = SCHEMAS[args.schema]; dims = [k for k, _ in schema["dims"]]
        buckets = defaultdict(list)
        for r in rows:
            buckets[(r["condition"], r["repo"])].append(r)
        rolled = []
        for (cond, repo), rs in buckets.items():
            merged = {}
            for k in dims:
                vals = [x["scores"].get(k) for x in rs if x["scores"].get(k) is not None]
                merged[k] = float(np.mean(vals)) if vals else None
            rolled.append({"instance_id": repo, "repo": repo, "condition": cond,
                           "resolved": None, "failure_classes": [], "scores": merged})
        rows = rolled
        print(f"[viz] rolled up to {len(rows)} per-repo series")

    schema = SCHEMAS[args.schema]
    stem = args.out or os.path.join("pcer", "figures", f"pcer_{args.mode}")
    os.makedirs(os.path.dirname(stem) or ".", exist_ok=True)
    args.stem = stem
    fig = MODES[args.mode](rows, schema, args)
    for fmt in [f.strip() for f in args.formats.split(",") if f.strip()]:
        path = f"{stem}.{fmt}"
        fig.savefig(path, dpi=args.dpi, bbox_inches="tight", facecolor="white")
        print(f"[viz] wrote {path}")


if __name__ == "__main__":
    main()