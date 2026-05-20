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
 monitoring/read_trace.py     — reads .eval log files
 monitoring/annotator.py      — risk-annotates every trace step
 monitoring/traces/           — stores annotated JSON files
 rag/indexer.py               — chunks and indexes Python files into ChromaDB
 rag/retriever.py             — semantic search over indexed code
 rag/chroma_db/               — local persistent vector store
 RAG connected to agent       — context retrieved before every task
