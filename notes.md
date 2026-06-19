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

### Next — Week 3
- Build PCER 5-dimension rubric
- Implement LLM judge scorer
- Human validation study (Cohen's Kappa)
