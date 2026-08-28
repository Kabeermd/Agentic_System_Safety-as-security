#!/usr/bin/env python
"""
make_kappa_sheet.py — build a BLIND rating sheet for Cohen's Kappa validation
of the two LLM-judged PCER dimensions (Reasoning Coherence, Recovery Rate).

It reads the 10 matched trajectories' .eval logs, extracts a readable summary of
each agent trajectory (its assistant reasoning turns + final outcome), and writes:

  pcer/kappa/kappa_rating_sheet.md   <- human-readable, read + score each trajectory
  pcer/kappa/kappa_blank.csv         <- fill RC_human / RR_human here (1-5)

The sheet does NOT contain the judge's scores, so your rating is independent
(blind rating is what makes the kappa valid).

Usage:
    python pcer/make_kappa_sheet.py
"""

import os
import json
from inspect_ai.log import read_eval_log

# the 10-trajectory matched pool (F6-corrected, deduplicated).
# maps (instance, condition) -> .eval log path
POOL = {
    ("astropy__astropy-12907", "arch"):     "results/2026-08-05T14-40-37-00-00_swe-bench-task_Bzw8ijSNswEnArPn2VmaVR.eval",
    ("astropy__astropy-14182", "arch"):     "results/2026-08-05T14-40-37-00-00_swe-bench-task_Bzw8ijSNswEnArPn2VmaVR.eval",
    ("astropy__astropy-14365", "arch"):     "results/2026-08-05T14-40-37-00-00_swe-bench-task_Bzw8ijSNswEnArPn2VmaVR.eval",
    ("astropy__astropy-12907", "baseline"): "results/2026-08-05T14-50-02-00-00_swe-bench-task_UnXhndzXfthWMBa65H765X.eval",
    ("astropy__astropy-14182", "baseline"): "results/2026-08-05T14-50-02-00-00_swe-bench-task_UnXhndzXfthWMBa65H765X.eval",
    ("astropy__astropy-14365", "baseline"): "results/2026-08-05T14-50-02-00-00_swe-bench-task_UnXhndzXfthWMBa65H765X.eval",
    ("django__django-10914", "arch"):       "results/2026-08-02T18-40-39-00-00_swe-bench-task_WxcxPMLUcbaXdCsrPr7xCz.eval",
    ("django__django-10924", "arch"):       "results/2026-08-02T18-40-39-00-00_swe-bench-task_WxcxPMLUcbaXdCsrPr7xCz.eval",
    ("django__django-10914", "baseline"):   "results/2026-08-02T22-32-02-00-00_swe-bench-task_hE6AWnAm4tLywNU367ThAF.eval",
    ("django__django-10924", "baseline"):   "results/2026-08-02T22-32-02-00-00_swe-bench-task_hE6AWnAm4tLywNU367ThAF.eval",
}

OUTDIR = "pcer/kappa"


def _sample_for(log, instance_id):
    for s in log.samples:
        if str(s.id) == instance_id or instance_id in str(s.id):
            return s
    return None


def _trace_summary(sample, max_steps=40, max_chars=600):
    """Readable trajectory: assistant reasoning + tool calls + final answer."""
    lines = []
    step = 0
    for m in sample.messages:
        role = getattr(m, "role", "?")
        if role == "assistant":
            step += 1
            if step > max_steps:
                lines.append("... (trace truncated) ...")
                break
            content = m.content if isinstance(m.content, str) else str(m.content)
            content = content.strip()
            if content:
                lines.append(f"  [assistant reasoning] {content[:max_chars]}")
            for tc in (getattr(m, "tool_calls", None) or []):
                fn = getattr(tc, "function", "?")
                args = getattr(tc, "arguments", {})
                argstr = json.dumps(args) if isinstance(args, dict) else str(args)
                lines.append(f"    -> tool: {fn}({argstr[:200]})")
        elif role == "tool":
            content = m.content if isinstance(m.content, str) else str(m.content)
            content = content.strip().replace("\n", " ")
            if content:
                lines.append(f"    <- result: {content[:220]}")
    return "\n".join(lines) if lines else "  (no trajectory extracted)"


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    # cache logs so we don't re-read the same .eval 3x
    log_cache = {}
    md = ["# PCER Kappa — blind rating sheet",
          "",
          "Score **Reasoning Coherence (RC)** and **Recovery Rate (RR)** for each",
          "trajectory on a **1-5** scale, using ONLY the trace below. Do not look at",
          "the judge's scores. Enter your scores in `kappa_blank.csv`.",
          "",
          "**Reasoning Coherence (1-5):** how clear/logical/goal-directed the reasoning",
          "chain is (5 = clean logical progression, 1 = disjointed/confused).",
          "",
          "**Recovery Rate (1-5):** how well the agent recovered from errors/dead-ends",
          "(5 = recovered cleanly or made no errors, 1 = failed to recover, looped).",
          "", "---", ""]
    csv_lines = ["instance_id,condition,RC_human,RR_human"]

    for i, ((inst, cond), path) in enumerate(POOL.items(), 1):
        if path not in log_cache:
            try:
                log_cache[path] = read_eval_log(path)
            except Exception as e:
                log_cache[path] = None
                print(f"[warn] could not read {path}: {e}")
        log = log_cache[path]
        sample = _sample_for(log, inst) if log else None

        md.append(f"## {i}. {inst}  ·  {cond}")
        md.append("")
        if sample is None:
            md.append("  (sample not found in log — check the .eval path/instance id)")
        else:
            resolved = None
            try:
                sc = next(iter(sample.scores.values()))
                resolved = getattr(sc, "value", None)
            except Exception:
                pass
            md.append(f"*resolved (capability): {resolved}*")
            md.append("")
            md.append("```")
            md.append(_trace_summary(sample))
            md.append("```")
        md.append("")
        md.append(f"**Your RC (1-5): ____   Your RR (1-5): ____**")
        md.append("")
        md.append("---")
        md.append("")
        csv_lines.append(f"{inst},{cond},,")

    with open(os.path.join(OUTDIR, "kappa_rating_sheet.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    with open(os.path.join(OUTDIR, "kappa_blank.csv"), "w", encoding="utf-8") as f:
        f.write("\n".join(csv_lines) + "\n")

    print(f"[kappa] wrote {OUTDIR}/kappa_rating_sheet.md  (read + score all 10)")
    print(f"[kappa] wrote {OUTDIR}/kappa_blank.csv        (fill RC_human, RR_human)")
    print("[kappa] rate all 10 blind, then run compute_kappa.py")


if __name__ == "__main__":
    main()