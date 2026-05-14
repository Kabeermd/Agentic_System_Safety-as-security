## Day 1 — Environment Setup Complete

- VS Code configured with all extensions
- .venv created and activated
- Inspect, ChromaDB, Groq, Datasets all installed
- DeepSeek Coder 16B running locally via Ollama — tested and working
- Groq API key configured

## Model Architecture — Final Decision

Development/testing:  DeepSeek Coder V2 16B (Ollama local) — fast iteration, no API costs (Qwen2.5 coder 7b deepseek not has tools to support)
Evaluation runs:      DeepSeek Coder V2 (Groq)(Qwen2.5 coder 7b deepseek not has tools to support) — reproducible results
CRM overseer:         Llama 3.3 70B (Groq) — strong policy reasoning
PCER judge:           Llama 3.3 70B (Groq) — complex evaluation task


## Week 1 Day 2
 Qwen2.5-Coder 7B via Ollama — working, supports tools
- ReAct agent running inside Inspect on SWE-bench Lite
- Agent reasoning correctly about astropy bugs
- Traces logging to ./results/
- Issue: submit() answer truncated — fix with --max-tokens 4096
- Tomorrow: add max_tokens, run 3 tasks cleanly, check trace logs