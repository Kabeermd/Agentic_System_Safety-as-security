"""
RedCode-Exec results visualisation.

Reads the frozen JSON (evaluation/scores/redcode_results.json) by default, or
derives live from current logs with --live.

Figures -> evaluation/scores/figures/:
  fig1_outcomes_taxonomy.png   Outcome distribution baseline vs enforcement (taxonomy lens)
  fig1b_outcomes_scorer.png    Outcome distribution baseline vs enforcement (scorer lens)
  fig2_by_format.png           Per-format outcome breakdown, baseline vs enforcement
  fig3_failure_classes.png     F1/F2/F5/F6 incidence, baseline vs enforcement
  fig4_transition_matrix.png   18-instance baseline->enforcement transition grid

Usage:
  python evaluation/redcode_visualize.py --json evaluation/scores/redcode_results.json
  python evaluation/redcode_visualize.py --live \
      --enforce-crm monitoring/crm_redcode_<enf>.jsonl \
      --baseline-crm monitoring/crm_redcode_<base>.jsonl \
      --enforce-eval results/<enf>.eval --baseline-eval results/<base>.eval
"""

import os
import sys
import json
import glob
import argparse
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch, FancyBboxPatch
import seaborn as sns

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# Design system  (one palette, one type scale, applied everywhere)

INK      = "#22223B"
MUTED    = "#7A7A93"
FAINT    = "#ECECF2"

# outcome palette (green / indigo / coral)
C_REFUSED  = "#3C9A7B"     # teal-green — model refused
C_PREVENT  = "#4A5FC1"     # indigo     — CRM prevented
C_EXECUTED = "#D9534F"     # coral-red  — executed (unsafe)
# muted variants for the "off/on" grouped bars in fig3
C_OFF      = "#D9534F"
C_ON       = "#4A5FC1"

OUTCOME_ORDER  = ["MODEL_REFUSED", "PREVENTED_CRM", "EXECUTED"]
OUTCOME_COLORS = {"MODEL_REFUSED": C_REFUSED, "PREVENTED_CRM": C_PREVENT, "EXECUTED": C_EXECUTED}
OUTCOME_LABEL  = {"MODEL_REFUSED": "Model refused", "PREVENTED_CRM": "Prevented by CRM",
                  "EXECUTED": "Executed (unsafe)"}
FORMATS = ["code", "summary", "details"]
FORMAT_LABEL = {"code": "Code", "summary": "Text summary", "details": "Text details"}

TITLE_FS, SUB_FS, LABEL_FS, TICK_FS, VAL_FS = 15, 10.5, 11.5, 11, 11


FONT_STACK = ["Calibri", "Times New Roman", "Georgia", "DejaVu Sans"]

sns.set_theme(style="whitegrid", context="talk")
plt.rcParams.update({
    "font.family": FONT_STACK,
    "figure.facecolor": "white", "axes.facecolor": "white",
    "axes.edgecolor": FAINT, "grid.color": FAINT, "grid.linewidth": 1.0,
    "text.color": INK, "axes.labelcolor": INK,
    "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.titleweight": "bold",
})


def _suptitle(fig, title, subtitle=None, x=0.5, ha="center"):
    """Two-line header: bold title with clear gap above a muted subtitle."""
    fig.suptitle(title, fontsize=TITLE_FS, fontweight="bold", x=x, ha=ha, y=1.02)
    if subtitle:
        fig.text(x, 0.94, subtitle, fontsize=SUB_FS, color=MUTED, ha=ha)


def _latest(pattern):
    files = glob.glob(pattern)
    return max(files, key=os.path.getmtime) if files else None


def _norm(counts):
    return {str(k).upper(): v for k, v in (counts or {}).items()}


def build_live_data(enforce_crm, baseline_crm, enforce_eval, baseline_eval):

    from evaluation.redcode_scores import taxonomy_lens, scorer_lens, transition_matrix
    
    data = {"taxonomy_lens": {
        "baseline":    taxonomy_lens(baseline_crm, enforce=False),
        "enforcement": taxonomy_lens(enforce_crm, enforce=True)}}
    if baseline_eval and enforce_eval:
        base_sc, enf_sc = scorer_lens(baseline_eval), scorer_lens(enforce_eval)
        data["scorer_lens"] = {"baseline": base_sc, "enforcement": enf_sc}
        data["transition_matrix"] = transition_matrix(base_sc, enf_sc) # type: ignore
    tb, te = data["taxonomy_lens"]["baseline"], data["taxonomy_lens"]["enforcement"]
    hl = {"taxonomy_F1_baseline": tb["aggregate_classes"]["F1"],
          "taxonomy_F1_enforcement": te["aggregate_classes"]["F1"],
          "taxonomy_executed_baseline": tb["aggregate_outcomes"].get("EXECUTED", 0),
          "taxonomy_prevented_enforcement": te["aggregate_outcomes"].get("PREVENTED_CRM", 0)}
    if "scorer_lens" in data:
        hl["scorer_accuracy_baseline"] = data["scorer_lens"]["baseline"]["accuracy"]
        hl["scorer_accuracy_enforcement"] = data["scorer_lens"]["enforcement"]["accuracy"]
    data["headline"] = hl
    return data



# Fig 1 / 1b — side-by-side donuts (baseline | enforcement) with safe-rate ring

def fig_outcomes(data, outdir, lens):
    key = f"{lens}_lens"
    if key not in data:
        print(f"  [skip] {lens} lens not in data")
        return
    base = _norm(data[key]["baseline"]["aggregate_outcomes"])
    enf  = _norm(data[key]["enforcement"]["aggregate_outcomes"])
    conds = [("Baseline", "CRM off / log-only", base),
             ("Enforcement", "CRM on", enf)]
    n_total = max(sum(base.values()), sum(enf.values())) or 1

    fig, ax = plt.subplots(figsize=(9.5, 5.2))
    xpos = [0, 1]
    bar_w = 0.5
    for (name, sub, totals), x in zip(conds, xpos):
        n = sum(totals.values()) or 1
        bottom = 0
        for o in OUTCOME_ORDER:
            v = totals.get(o, 0)
            if not v:
                continue
            ax.bar(x, v, bottom=bottom, width=bar_w, color=OUTCOME_COLORS[o],
                   edgecolor="white", linewidth=2.5, zorder=3)
            pct = 100*v/n
            ax.text(x, bottom + v/2, f"{v}   {pct:.0f}%", ha="center", va="center",
                    color="white", fontweight="bold", fontsize=VAL_FS, zorder=4)
            bottom += v
        # safe-rate callout above each bar
        safe = totals.get("MODEL_REFUSED", 0) + totals.get("PREVENTED_CRM", 0)
        ax.text(x, n_total + 2.3, f"{100*safe/n:.0f}%", ha="center", va="bottom",
                fontsize=22, fontweight="bold",
                color=C_PREVENT if name == "Enforcement" else INK)
        ax.text(x, n_total + 1.75, "safe", ha="center", va="bottom",
                fontsize=11, color=MUTED)

    ax.set_xticks(xpos)
    ax.set_xticklabels([f"{c[0]}\n{c[1]}" for c in conds], fontsize=TICK_FS)
    ax.set_ylabel("Number of instances", fontsize=LABEL_FS)
    ax.set_ylim(0, n_total + 4.2)
    ax.set_xlim(-0.6, 1.6)
    ax.grid(axis="x", visible=False)
    sns.despine(ax=ax)
    handles = [Patch(facecolor=OUTCOME_COLORS[o], label=OUTCOME_LABEL[o]) for o in OUTCOME_ORDER]
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.20),
              ncol=3, frameon=False, fontsize=11)
    _suptitle(fig, f"RedCode-Exec outcomes  -  {lens} lens",
              "Unsafe executions under baseline become CRM-prevented under enforcement")
    fig.tight_layout(rect=[0, 0.04, 1, 0.88])    # type: ignore
    fn = "fig1_outcomes_taxonomy.png" if lens == "taxonomy" else "fig1b_outcomes_scorer.png"
    out = os.path.join(outdir, fn)
    fig.savefig(out, dpi=170, bbox_inches="tight"); plt.close(fig)
    print(f"  wrote {out}")



# Fig 2 — per-format stacked, baseline | enforcement

def fig_by_format(data, outdir):
    tm = data.get("transition_matrix")
    if not tm:
        print("  [skip] no transition_matrix -> fig2 needs scorer lens")
        return
    base = {f: defaultdict(int) for f in FORMATS}
    enf  = {f: defaultdict(int) for f in FORMATS}
    for r in tm:
        f = r["format"]
        if f not in FORMATS:
            continue
        if r["baseline"]:    base[f][str(r["baseline"]).upper()] += 1
        if r["enforcement"]: enf[f][str(r["enforcement"]).upper()] += 1

    fig, axes = plt.subplots(1, 2, figsize=(12.5, 5.2), sharey=True)
    for ax, tally, title in ((axes[0], base, "Baseline - CRM off"),
                             (axes[1], enf, "Enforcement - CRM on")):
        x = range(len(FORMATS)); bottoms = [0]*len(FORMATS)
        for o in OUTCOME_ORDER:
            vals = [tally[f].get(o, 0) for f in FORMATS]
            ax.bar(list(x), vals, bottom=bottoms, width=0.62,
                   color=OUTCOME_COLORS[o], edgecolor="white", linewidth=2)
            for i, (v, b) in enumerate(zip(vals, bottoms)):
                if v:
                    ax.text(i, b+v/2, str(v), ha="center", va="center",
                            color="white", fontweight="bold", fontsize=VAL_FS)
            bottoms = [b+v for b, v in zip(bottoms, vals)]
        ax.set_xticks(list(x))
        ax.set_xticklabels([FORMAT_LABEL[f] for f in FORMATS], fontsize=TICK_FS)
        ax.set_title(title, fontsize=LABEL_FS+1, fontweight="bold", loc="center", pad=10)
        ax.set_ylim(0, 6.6)
        ax.grid(axis="x", visible=False)
        sns.despine(ax=ax, left=True)
        ax.tick_params(left=False)
    axes[0].set_ylabel("Number of instances", fontsize=LABEL_FS)
    handles = [Patch(facecolor=OUTCOME_COLORS[o], label=OUTCOME_LABEL[o]) for o in OUTCOME_ORDER]
    fig.legend(handles=handles, loc="lower center", ncol=3, frameon=False,
               fontsize=11, bbox_to_anchor=(0.5, -0.08))
    _suptitle(fig, "Outcome by prompt format",
              "Code triggers the model's own refusal; softened natural-language variants "
              "slip past the model but are caught by the CRM")
    fig.tight_layout(rect=[0, 0.08, 1, 0.88])    # type: ignore
    out = os.path.join(outdir, "fig2_by_format.png")
    fig.savefig(out, dpi=170, bbox_inches="tight"); plt.close(fig)
    print(f"  wrote {out}")



# Fig 3 — failure-class incidence (grouped bars)

def fig_classes(data, outdir):
    tax = data["taxonomy_lens"]
    base = tax["baseline"]["aggregate_classes"]; enf = tax["enforcement"]["aggregate_classes"]
    classes = ["F1", "F2", "F5", "F6"]
    sub = {"F1": "Unsafe\nexecution", "F2": "Boundary\nviolation",
           "F5": "Override /\nevasion", "F6": "Disguise /\nshortcut"}
    x = range(len(classes)); w = 0.36
    fig, ax = plt.subplots(figsize=(9.5, 5.6))
    bvals = [base.get(c, 0) for c in classes]; evals = [enf.get(c, 0) for c in classes]
    ax.bar([i-w/2 for i in x], bvals, width=w, label="Baseline (CRM off)",
           color=C_OFF, edgecolor="white", linewidth=1.5, zorder=3)
    ax.bar([i+w/2 for i in x], evals, width=w, label="Enforcement (CRM on)",
           color=C_ON, edgecolor="white", linewidth=1.5, zorder=3)
    for i, v in enumerate(bvals):
        ax.text(i-w/2, v+0.12, str(v), ha="center", va="bottom", fontweight="bold", fontsize=VAL_FS)
    for i, v in enumerate(evals):
        ax.text(i+w/2, v+0.12, str(v), ha="center", va="bottom", fontweight="bold", fontsize=VAL_FS)
    # highlight the F1 collapse with a clean callout box
    if bvals[0] and not evals[0]:
        ax.annotate(
            f"F1 collapses\n{bvals[0]} → {evals[0]}",
            xy=(0 + w/2, 0.2), xytext=(0.75, max(bvals+evals)*0.7),
            fontsize=11, fontweight="bold", color=INK, ha="center", va="center",
            bbox=dict(boxstyle="round,pad=0.5", facecolor="#FBEAEA",
                      edgecolor=C_OFF, linewidth=1.5),
            arrowprops=dict(arrowstyle="-|>", color=C_OFF, lw=1.8,
                            connectionstyle="arc3,rad=0.2"))
    ax.set_xticks(list(x))
    ax.set_xticklabels([f"{c}\n{sub[c]}" for c in classes], fontsize=TICK_FS)
    ax.set_ylabel("Instances exhibiting class", fontsize=LABEL_FS)
    ax.set_ylim(0, max(bvals+evals)+1.2)
    ax.grid(axis="x", visible=False); sns.despine(ax=ax)
    ax.legend(frameon=False, fontsize=11, loc="upper right")
    _suptitle(fig, "Failure-class incidence  -  baseline vs enforcement",
              "F1 unsafe-execution collapses under the CRM; F2/F5 attempts persist but are blocked")
    fig.tight_layout(rect=[0, 0, 1, 0.90]) # type: ignore
    out = os.path.join(outdir, "fig3_failure_classes.png")
    fig.savefig(out, dpi=170, bbox_inches="tight"); plt.close(fig)
    print(f"  wrote {out}")



# Fig 4 — transition grid

def _cell(ax, cx, cy, w, h, color, label):
    ax.add_patch(FancyBboxPatch((cx-w/2, cy-h/2), w, h,
                 boxstyle="round,pad=0.006,rounding_size=0.07",
                 facecolor=color, edgecolor="white", linewidth=2))
    ax.text(cx, cy, label, ha="center", va="center", color="white",
            fontsize=9.5, fontweight="bold")


def fig_transition(data, outdir):
    tm = data.get("transition_matrix")
    if not tm:
        print("  [skip] no transition_matrix -> fig4 needs scorer lens")
        return
    rows = sorted(tm, key=lambda r: r["instance"]); n = len(rows)
    fig, ax = plt.subplots(figsize=(9.5, max(6, 0.5*n)))
    ax.set_xlim(0, 3.3); ax.set_ylim(0, n+1.4); ax.axis("off")
    ax.text(1.62, n+1.0, "Per-instance transition:  baseline → enforcement",
            ha="center", fontsize=TITLE_FS, fontweight="bold", color=INK)
    for cx, lab in ((0.55, "Instance"), (1.55, "Baseline"), (2.68, "Enforcement")):
        ax.text(cx, n+0.3, lab, ha="center", fontweight="bold", fontsize=11.5, color=MUTED)
    for idx, r in enumerate(rows):
        y = n - idx - 0.5
        b = str(r["baseline"] or "").upper(); e = str(r["enforcement"] or "").upper()
        ax.text(0.55, y, r["instance"].replace("redcode-", ""),
                ha="center", va="center", fontsize=10, family="monospace", color=INK)
        _cell(ax, 1.55, y, 0.92, 0.74, OUTCOME_COLORS.get(b, "#B7BAC6"),
              OUTCOME_LABEL.get(b, b).split()[0])
        _cell(ax, 2.68, y, 0.92, 0.74, OUTCOME_COLORS.get(e, "#B7BAC6"),
              OUTCOME_LABEL.get(e, e).split()[0])
        if b != e:
            ax.annotate("", xy=(2.20, y), xytext=(2.02, y),
                        arrowprops=dict(arrowstyle="-|>", color=INK, lw=1.6))
    handles = [Patch(facecolor=OUTCOME_COLORS[o], label=OUTCOME_LABEL[o]) for o in OUTCOME_ORDER]
    ax.legend(handles=handles, loc="lower center", ncol=3, frameon=False,
              fontsize=11, bbox_to_anchor=(0.5, -0.07))
    fig.tight_layout()
    out = os.path.join(outdir, "fig4_transition_matrix.png")
    fig.savefig(out, dpi=170, bbox_inches="tight"); plt.close(fig)
    print(f"  wrote {out}")


def main():
    ap = argparse.ArgumentParser(description="Visualise RedCode-Exec results.")
    ap.add_argument("--json", default="evaluation/scores/redcode_results.json")
    ap.add_argument("--outdir", default="evaluation/scores/figures")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--enforce-crm", default=None)
    ap.add_argument("--baseline-crm", default=None)
    ap.add_argument("--enforce-eval", default=None)
    ap.add_argument("--baseline-eval", default=None)
    ap.add_argument("--dump-json", default=None)
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)

    if args.live:
        enforce_crm = args.enforce_crm or _latest("monitoring/crm_redcode_*.jsonl")
        if not args.baseline_crm:
            ap.error("--live needs --baseline-crm.")
        if not enforce_crm:
            ap.error("no enforcement CRM log found; pass --enforce-crm.")
        print(f"[viz][live] enforce-crm={enforce_crm}\n[viz][live] baseline-crm={args.baseline_crm}")
        data = build_live_data(enforce_crm, args.baseline_crm, args.enforce_eval, args.baseline_eval)
        if args.dump_json:
            os.makedirs(os.path.dirname(args.dump_json) or ".", exist_ok=True)
            with open(args.dump_json, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            print(f"[viz][live] wrote {args.dump_json}")
    else:
        with open(args.json, encoding="utf-8") as f:
            data = json.load(f)
        print(f"[viz] reading frozen {args.json}")

    print(f"[viz] headline: {json.dumps(data.get('headline', {}), indent=2)}\n")
    fig_outcomes(data, args.outdir, "taxonomy")
    fig_outcomes(data, args.outdir, "scorer")
    fig_by_format(data, args.outdir)
    fig_classes(data, args.outdir)
    fig_transition(data, args.outdir)
    print("\n[viz] done.")


if __name__ == "__main__":
    main()