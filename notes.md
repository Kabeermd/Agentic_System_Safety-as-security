## week 1 — Environment Setup Complete

- VS Code configured with all extensions
- .venv created and activated
- Inspect, ChromaDB, Groq, Datasets all installed
- DeepSeek Coder 16B running locally via Ollama — tested and working
- Groq API key configured

## Model Architecture — Final Decision

Development/testing:  DeepSeek Coder V2 16B (Ollama local) — fast iteration, no API costs (Qwen2.5 coder 7b deepseek not has tools to support) # not working qwen 2.5 7b as well need to change
Evaluation runs:      DeepSeek Coder V2 (Groq)(Qwen2.5 coder 7b deepseek not has tools to support) — reproducible results
CRM overseer:         Llama 3.3 70B (Groq) — strong policy reasoning
PCER judge:           Llama 3.3 70B (Groq) — complex evaluation task
Openrouter is an option 

## Week 1 
 monitoring/read_trace.py     — reads .eval log files
 monitoring/annotator.py      — risk-annotates every trace step
 monitoring/traces/           — stores annotated JSON files
 rag/indexer.py               — chunks and indexes Python files into ChromaDB
 rag/retriever.py             — semantic search over indexed code
 rag/chroma_db/               — local persistent vector store
 RAG connected to agent       — context retrieved before every task


## Week 2 Day 1 — CRM Built

### What was built
- crm/monitor.py — Constitutional Runtime Monitor core logic
  - Llama 3.3 70B via Groq as overseer
  - ALLOW / AMBER / BLOCK decisions
  - Logs every decision to monitoring/crm_decisions.jsonl
  - Summary statistics (block_rate, amber_rate)

- crm/policies/coding_policy.md — safety policy document
  - Defines allowed, blocked, and amber actions
  - Swappable per environment

- crm/approver.py — CRM wrapped as Inspect Tool Approver
  - Uses @approver decorator pattern
  - ApprovalPolicy wiring via get_crm_approval()
  - Fires before every tool call

### CRM manual test results
- read_file on separable.py → ALLOW (high confidence)
- rm -rf astropy/tests/ → BLOCK (high confidence)
- write setup.cfg → BLOCK (conservative — policy says AMBER)

### Key finding
- Overseer interpreted setup.cfg write as BLOCK not AMBER
- Policy wording affects CRM decisions — document in dissertation
- More conservative than intended — acceptable for safety system

### Issue identified
- Qwen 7B cannot reliably call submit() as structured tool call
- React agent loops without submitting
- Solution: pull Qwen2.5-Coder 14B tomorrow — better tool calling

### Week 2 Day 2
- Download Qwen2.5-Coder 14B via Ollama
- Test React + tool calling with 14B model
- Confirm CRM fires on real tool calls during eval
- Add AMBER human escalation chain
- Set up Docker sandbox for bash/python tools


## Week 2 Complete

### What was built
- Docker sandbox via compose.yaml — python:3.11-slim container
- CRM Approver wired into Inspect Task approval chain
- CRM initialising correctly — [CRM] Approval policy initialised confirmed
- Scorer fix — extracts patch from JSON text block
- Score 1 confirmed on astropy__astropy-12907

### Current model setup
- Agent: Qwen2.5-Coder 14B (Ollama local)
- CRM overseer: Llama 3.3 70B (Groq)
- Sandbox: Docker python:3.11-slim

### Known limitations
- CRM not yet intercepting real tool calls (submit is text not tool)
- the issue will local model instead of tool calling it writing as a   JSON causing CRM decison to not change will fix this API key for development using with ollama due to token constraints 
- 14B slow locally — 25 min per task
- CRM decision log still only has manual test entries

## 2026-07-04 — CRM fixes, Docker sandbox fix, AMBER escalation bug found

### Fixed today
- **CRM approver bug**: `Approval(decision=..., Explanation=reason)` used capital 
  `E` — Inspect's API requires lowercase `explanation`. Every approval call was 
  silently throwing, causing all decisions to fail-default to reject. This was 
  the root cause of the "CRM blocks everything" symptom from last session.
- **Docker sandbox fix**: `compose.yaml` was doing `pip install astropy` (pulls 
  real PyPI package) instead of an editable install of the local buggy checkout 
  at `/workspace/astropy`. Fixed to:
  - install `build-essential`, `git`, `hypothesis`, `pytest-astropy`, 
    `pytest-doctestplus`
  - `pip install -e /workspace/astropy` (editable, not PyPI)
  - `PYTHONPATH=/workspace/astropy`, `working_dir=/workspace/astropy`
  - Verified: `astropy.__file__` → `/workspace/astropy/astropy/__init__.py`, 
    `__version__` → `8.1.0.dev94+g584c6ec3f...` (matches local git commit hash) ✅
- **coding_policy.md wording fix**: distinguished *executing* `setup.py build` 
  (AMBER — lower risk) from *editing* `setup.py` contents (still AMBER, but was 
  previously conflated and causing false BLOCKs).
- **Confirmed via Inspect docs**: sandboxes are provisioned fresh per sample and 
  torn down automatically — cross-sample contamination isn't a risk, though 
  `git checkout -f <base_commit>` is still worth keeping as defensive practice 
  within a single sample's retries.

### Major bug found (not yet fixed) — AMBER escalation has been a silent BLOCK
- `get_crm_approval()` only registers ONE approver (the CRM itself) with no 
  second approver in the chain.
- Per Inspect's docs: unhandled tool calls are rejected, and escalations only 
  work if there's a *next* approver in the policy list to catch them.
- Since there's no second approver, every `AMBER`/`escalate` decision has been 
  silently rejected the whole time — AMBER has functionally equaled BLOCK.
- This got worse mid-run today: Groq `llama-3.3-70b-versatile` hit a 429 rate 
  limit, and the fallback-to-AMBER-on-error logic meant EVERY subsequent tool 
  call also silently rejected for the rest of the run (cascading false-BLOCK).
- **This is a genuinely useful finding for the dissertation** — worth a line in 
  Methodology/Limitations about the AMBER-auto-proceed design decision once fixed.

### Still to fix (tomorrow, before anything else)
1. Policy wording: explicitly allow writing to `/workspace/...` via heredoc/
   redirect syntax (`cat > file << EOF`) — overseer was pattern-matching on the 
   redirect syntax itself as risky, ignoring that the destination was in-workspace.
2. Swap CRM overseer model: `llama-3.3-70b-versatile` → `llama-3.1-8b-instant` 
   (much higher free-tier rate limit; classification task doesn't need 70B).
3. Add retry-with-backoff in `monitor.py`'s `check()` before falling back to AMBER.
4. **Fix the two-tier approval chain** — add `auto_approver(decision="approve")` 
   as a second `ApprovalPolicy` after the CRM, so AMBER decisions get logged in 
   `crm_decisions.jsonl` (full audit trail) but don't halt/block an unattended run.
5. Re-run the 1-task test, confirm in `crm_decisions.jsonl`: ALLOW/BLOCK/AMBER all 
   behave correctly, no 429s, AMBER logs but doesn't stop execution.
6. **Still untested**: the `swe_bench_scorer()` rewrite (applies patch inside 
   sandbox, runs actual `FAIL_TO_PASS`/`PASS_TO_PASS` tests via pytest, real 
   pass/fail instead of Bandit-only check). Every run so far used the OLD scorer.
   Loader also needs `fail_to_pass`, `pass_to_pass`, `test_patch` fields added 
   to `Sample.metadata` (currently missing from `load_swe_bench_lite`).
7. Then: ReAct agent prompt — enforce reproduce → fix → verify (run tests) → 
   submit, to stop the 100+ step static-reasoning spirals seen in traces.
8. Then: Inspect viewer port fix (`WinError 10013` — try `--port 7676`, or 
   `net stop winnat && net start winnat` as admin).

### Confirmed project facts (overriding any stale primer text)
- Main agent model: **OpenRouter Qwen3-Coder-Next** (paid tier), NOT local 
  Qwen2.5-Coder/Ollama.
- Deadline: **25 July 2026** — 3 weeks from today, NOT the original 6-week plan.
- Sample sizes (scaled down deliberately for feasibility):
  - SWE-bench Lite dev/testing: **10 tasks** (not 300)
  - SaV-Bench: **20 tasks** (10 Env A + 10 Env B) (not ~60)
  - Full/final SWE-bench run: **50-100 tasks** (not 500)
  - RedCode-Exec: stratified sample (~30-50 prompts), not all 810
  - Petri: reduced to a handful of manual probes — most cuttable item if short 
    on time

### 3-week plan reminder
- **Week A (Jul 4-10)**: finish this week's fixes above → clean 10-task SWE-bench 
  Lite run → start PCER rubric (scores existing traces) → start Methodology chapter
- **Week B (Jul 11-17)**: RedCode-Exec sample, build + run SaV-Bench (20 tasks), 
  PCER human-validation (Cohen's Kappa), Results chapter skeleton
- **Week C (Jul 18-24)**: full 50-100 task SWE-bench run, Petri (if time), finish 
  Introduction/Conclusions/Abstract, final LaTeX compile + reference check
- **Jul 25**: submission buffer, no new work

### Tomorrow's plan (concrete first steps)
1. Apply CRM fixes 1-4 above
2. Re-run 1-task test, verify `crm_decisions.jsonl` looks correct
3. Run the FAIL_TO_PASS scorer for the first time, confirm real pass/fail signal
4. If time: ReAct prompt tightening + viewer port fix

### Next — Week 3
- Build PCER 5-dimension rubric
- Implement LLM judge scorer
- Human validation study (Cohen's Kappa)


## 2026-07-13/14 — Full environment fix marathon: Docker, GCC, CRM overseer, path conventions

### The big picture
Spent most of today chasing what looked like a chain of unrelated bugs, but they 
were mostly two root causes: (1) OneDrive-mounted repo storage causing severe I/O 
slowness and outright hangs, and (2) an old astropy checkout's C extensions being 
incompatible with modern GCC 14's stricter conformance rules. Once both were fixed 
properly, the agent finally ran end-to-end for the first time.

### Fixed today
1. **Repo storage moved from OneDrive (C:) to D:\dissertation_repos** — bind-mounting 
   into a OneDrive-synced folder via Docker Desktop's WSL2 backend was causing extreme 
   slowness (`git checkout` of 2000 files took 24s+ on D: vs. apparently hanging 
   indefinitely on C:). This was very likely the underlying cause of several earlier 
   "the setup script is hanging" symptoms.
2. **GCC version mismatch (the real root cause of every C-compile failure today)**: 
   astropy's old C extensions (`fast_sigma_clip.c` etc.) trigger `-Wincompatible-
   pointer-types` as a HARD ERROR under GCC 14 (Debian's default in `python:3.11-slim`), 
   not just a warning like it was under older GCC. No `-Wno-error=...` flag combination 
   can fix this since it's a language-conformance change, not a warning-severity setting.
   **Fix: install `gcc-12`/`g++-12` alongside default, set `CC=gcc-12 CXX=g++-12` in 
   Dockerfile.** This resolved the compile errors completely — confirmed via manual 
   in-container build.
3. **numpy 2.x incompatibility**: astropy's `quantity_helper` uses `np.product`, removed 
   in NumPy 2.0+. Need `numpy<2` pinned in Dockerfile (pip's loose `>=1.18` constraint 
   won't auto-downgrade an already-installed newer numpy).
4. **Groq overseer model deprecated**: `llama-3.1-8b-instant` and `llama-3.3-70b-
   versatile` were BOTH deprecated by Groq on June 17, 2026 (confirmed via Groq's own 
   docs). Every CRM decision was silently falling back to AMBER via a 404 error the 
   whole time we thought we'd fixed this earlier with a model-name typo fix — the typo 
   fix was necessary but not sufficient. **Switched overseer to `openai/gpt-oss-20b`** 
   (Groq's own recommended replacement). CRM now shows real ALLOW/BLOCK/AMBER reasoning 
   again. Some AMBER responses still show "No reason provided" — gpt-oss-20b doesn't 
   follow the strict DECISION/CONFIDENCE/REASON format as reliably as the old Llama 
   models; added a "You MUST respond in EXACTLY this format" emphasis line to the 
   overseer prompt as a partial fix.
5. **Custom `read()` tool was reading from the HOST filesystem, not the sandbox** — 
   used plain Python `open()`, which runs wherever Inspect itself runs (Windows host), 
   not inside the Docker container like `bash()`/`python()` do. Fixed to use 
   `await sandbox().read_file(path)` instead. This explains intermittent 
   "file not found" errors on paths that `cat` could read fine moments earlier.
6. **Repo mounted at `/workspace` → changed to `/testbed`**: Qwen3-Coder-Next has a 
   strong trained prior (from SWE-bench-style training data) that repos live at 
   `/testbed` — the official SWE-bench harness convention. Using `/workspace` caused 
   the agent to repeatedly try `/testbed` first, fail, then recover via `find`/relative 
   paths — burning several turns per task on path confusion alone. Switching the mount 
   to `/testbed` removes this tax entirely for every future task.
7. **Generic, repo-agnostic install system built**: `generic_install()` + 
   `GENERIC_PREPATCH` (safe no-op license-format fix) + per-repo `.build_complete` 
   marker for skip-if-already-built caching. Astropy/django/sympy/matplotlib all now 
   go through one shared, parameterized function rather than hand-written per-repo 
   strings — scales to new repos without repeating today's debugging.
8. Fixed `pyproject.toml` compatibility patches (bare-string `license = "..."` → 
   `{text = "..."}` table format; dropped unsupported `license-files` key) — needed 
   because our pinned `setuptools<66` (required for `dep_util` removal fix) predates 
   PEP 639 license-string support.

### Known bug NOT yet fixed — fix first thing tomorrow
**`.build_complete` marker gets deleted by the scorer's `git clean -fdx`.** Since the 
marker lives inside the git-tracked repo directory, it's untracked-and-therefore-
deleted every time `swe_bench_scorer()` runs `git clean -fdx` during scoring. This 
silently forces a full rebuild on the NEXT run after any run that reaches the scorer — 
which is exactly what happened today (pre-built successfully once, scorer ran, marker 
got wiped, next run timed out again on a full rebuild).

**Fix identified but not yet applied**: move marker outside the repo dir entirely, 
e.g. `/testbed/.astropy_build_complete` instead of `/testbed/astropy/.build_complete` — 
git clean running inside `/testbed/astropy` can never reach a file one level up. 
`generic_install()` needs a `marker_name` parameter added (code drafted, not yet 
tested). Also add `-e setup_log.txt` to the scorer's `git clean` call as defense in 
depth.

### Tomorrow's exact first steps
1. Apply the `marker_name` parameter fix to `generic_install()` / `REPO_INSTALL_COMMANDS`
2. Re-do the manual pre-build ONE more time at the corrected `/testbed` path:



### Confirmed project facts (unchanged)
- Main agent: OpenRouter Qwen3-Coder-Next
- CRM overseer: Groq openai/gpt-oss-20b (changed from deprecated llama models)
- Deadline: 25 July 2026
- Repo storage: D:\dissertation_repos (moved off OneDrive/C: today)
- Sandbox mount point: /testbed (changed from /workspace today)