#!/usr/bin/env python
"""
compute_kappa.py — Cohen's weighted Kappa for the two LLM-judged PCER dimensions
(Reasoning Coherence, Recovery Rate), human rater vs Claude Haiku 4.5 judge.

Reads:
  - pcer/kappa/kappa_blank.csv   (your blind ratings: instance_id,condition,RC_human,RR_human)
  - the 4 F6-corrected judge score files (judge's RC/RR)

Reports, PER DIMENSION:
  - N rated
  - raw exact agreement (%)  <- often the more honest number on small skewed samples
  - linearly-weighted Cohen's kappa (ordinal-appropriate: near-misses penalised less)
  - unweighted kappa (for reference)
  - interpretation band

NOTE on small N: with n=10 and clustered scores, kappa is unstable and sensitive to
skewed marginals (the "kappa paradox"). Report it as an INDICATIVE agreement check,
disclose N, and lead with weighted kappa + raw agreement together.

Usage:
    python pcer/compute_kappa.py
"""

import os
import csv
import json
import glob

JUDGE_FILES = [
    "pcer/scores/pcer_astropy_arch_20260805T161055.jsonl",
    "pcer/scores/pcer_astropy_baseline_20260805T161308.jsonl",
    "pcer/scores/pcer_django_arch_20260805T161828.jsonl",
    "pcer/scores/pcer_django_baseline_20260805T161841.jsonl",
]
RATINGS_CSV = "pcer/kappa/kappa_blank.csv"
DIMS = [("RC", "reasoning_coherence"), ("RR", "recovery_rate")]
SCALE = [1, 2, 3, 4, 5]


def load_judge():
    out = {}
    for f in JUDGE_FILES:
        for line in open(f, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            key = (r["instance_id"], r["condition"])
            out[key] = {"reasoning_coherence": r["scores"].get("reasoning_coherence"),
                        "recovery_rate": r["scores"].get("recovery_rate")}
    return out


def load_human():
    out = {}
    with open(RATINGS_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key = (row["instance_id"], row["condition"])
            rc = row.get("RC_human", "").strip()
            rr = row.get("RR_human", "").strip()
            out[key] = {"reasoning_coherence": int(rc) if rc else None,
                        "recovery_rate": int(rr) if rr else None}
    return out


def weighted_kappa(a, b, weights="linear"):
    """Cohen's weighted kappa for two equal-length integer rating lists over SCALE."""
    n = len(a)
    if n == 0:
        return None
    k = len(SCALE)
    idx = {v: i for i, v in enumerate(SCALE)}

    # observed matrix
    O = [[0]*k for _ in range(k)]
    for x, y in zip(a, b):
        O[idx[x]][idx[y]] += 1

    # weight matrix
    W = [[0.0]*k for _ in range(k)]
    for i in range(k):
        for j in range(k):
            d = abs(i - j)
            if weights == "linear":
                W[i][j] = d / (k - 1)
            elif weights == "quadratic":
                W[i][j] = (d / (k - 1)) ** 2
            else:  # unweighted
                W[i][j] = 0.0 if i == j else 1.0

    # marginals -> expected matrix
    row = [sum(O[i]) for i in range(k)]
    col = [sum(O[i][j] for i in range(k)) for j in range(k)]
    E = [[row[i]*col[j]/n for j in range(k)] for i in range(k)]

    num = sum(W[i][j]*O[i][j] for i in range(k) for j in range(k))
    den = sum(W[i][j]*E[i][j] for i in range(k) for j in range(k))
    if den == 0:
        # perfect-agreement-with-no-variance edge case
        return 1.0 if num == 0 else 0.0
    return 1.0 - num/den


def band(k):
    if k is None: return "n/a"
    if k < 0:    return "poor (worse than chance)"
    if k < 0.20: return "slight"
    if k < 0.40: return "fair"
    if k < 0.60: return "moderate"
    if k < 0.80: return "substantial"
    return "almost perfect"


def main():
    if not os.path.exists(RATINGS_CSV):
        raise SystemExit(f"{RATINGS_CSV} not found — run make_kappa_sheet.py and fill it first.")
    judge, human = load_judge(), load_human()

    print("="*66)
    print(" PCER inter-rater agreement — human vs Claude Haiku 4.5 judge")
    print("="*66)

    for short, key in DIMS:
        pairs = []
        for k_ in judge:
            jv = judge[k_].get(key)
            hv = human.get(k_, {}).get(key)
            if jv is not None and hv is not None:
                pairs.append((hv, jv))
        if not pairs:
            print(f"\n{short}: no rated pairs (fill {RATINGS_CSV})")
            continue
        h = [p[0] for p in pairs]; j = [p[1] for p in pairs]
        n = len(pairs)
        exact = sum(1 for x, y in pairs if x == y) / n
        within1 = sum(1 for x, y in pairs if abs(x-y) <= 1) / n
        kw = weighted_kappa(h, j, "linear")
        kq = weighted_kappa(h, j, "quadratic")
        ku = weighted_kappa(h, j, "unweighted")

        print(f"\n{short}  ({key})   N={n}")
        print(f"  raw exact agreement : {exact*100:5.1f}%")
        print(f"  within-1 agreement  : {within1*100:5.1f}%")
        print(f"  kappa (unweighted)  : {ku:+.3f}   [{band(ku)}]")
        print(f"  kappa (linear wt)   : {kw:+.3f}   [{band(kw)}]")
        print(f"  kappa (quadratic wt): {kq:+.3f}   [{band(kq)}]")
        print("  pairs (human, judge): " + ", ".join(f"({x},{y})" for x, y in pairs))

    print("\n" + "-"*66)
    print(" Report the LINEAR-weighted kappa (ordinal-appropriate) alongside raw")
    print(" agreement. Disclose N and treat as an indicative check given small N.")
    print("-"*66)


if __name__ == "__main__":
    main()