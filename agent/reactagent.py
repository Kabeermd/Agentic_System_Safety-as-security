import sys
from datasets import load_dataset
from inspect_ai import Task, task, eval
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.solver import generate, system_message
from inspect_ai.agent import Agent, agent, react
from inspect_ai.tool import bash, python
from inspect_ai.scorer import exact,scorer, Score, accuracy, stderr
from dotenv import load_dotenv
import os

# add project root to path so we can import rag module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# import RAG retriever for context retrieval in task setup
from rag.retriever import retrieve_context, format_context
load_dotenv()

#verifier imports for trace analysis
from evaluation.verifier import verify_patch


#CRM imports
from crm.approver import get_crm_approval


# Loading SWE-bench Lite 
def load_swe_bench_lite(n=1):
    """Load n tasks from SWE-bench Lite as Inspect Samples."""
    dataset = load_dataset(
        "princeton-nlp/SWE-bench_Lite",
        split="test",
        token=os.getenv("HF_TOKEN")
    )

    samples = []
    for i in range(n):
        task_data = dataset[i]
        # retrieve RAG context for this issue
        # NOTE: for now using test_repo — Week 2 we index real repos

        # using astropy for testing RAG retrieval and formatting

        context_chunks = retrieve_context(
            issue_text=task_data["problem_statement"],
            repo_name="astropy/astropy",
            n_results=3
        )
        rag_context = format_context(context_chunks)

        # prepend RAG context to the input
        full_input = (
            f"{rag_context}\n\n"
            f"ISSUE:\n{task_data['problem_statement']}"
            if rag_context
            else task_data["problem_statement"]
        )

        samples.append(
            Sample(
                id=task_data["instance_id"],
                input=full_input,
                metadata={
                    "repo":        task_data["repo"],
                    "base_commit": task_data["base_commit"],
                    "instance_id": task_data["instance_id"],
                    "rag_used":    bool(rag_context)
                }
            )
        )
    return MemoryDataset(samples=samples, name="swe-bench-lite")


# Building the ReAct Agent
"""@agent
def coding_agent(a) -> Agent:
   return react(
        tools=[bash, python],
        attempts=2,
        system_prompt=(
            "You are a helpful and precise coding assistant. "
            "Use the provided tools to solve the given programming problem. "
            "Always try to solve the problem with the least number of steps possible."
        )
    )"""

@agent
def coding_agent() -> Agent:
    return react(
        prompt=(
            "You are an expert software engineer. "
            "You have been given relevant code context and a bug report. "
            "Use the python tool to investigate and understand the bug, "
            "then write a git diff patch that fixes it. "
            "When ready, call submit() with your git diff patch." 
            "NOTE - submit() is a tool call it directly like any other tool."
            "Do not write JSON manually. Call submit() as a function" 
            
        ),
        tools=[python(),bash()],
        attempts=3,
    )

import re
import json

@scorer(metrics=[accuracy(), stderr()])
def record_output():
    async def score(state, target):
        raw = state.output.completion

        # extract patch from JSON submit block if model wrote it as text
        patch = raw 

        try:
            #strip markdown code fences
            clean = re.sub(r'```json\s*|\s*```', '', raw).strip()
            data = json.loads(clean)
            # handle {"name": "submit", "arguments": {"answer": "..."}}
            if isinstance(data, dict):
                if "arguments" in data:
                    patch = data["arguments"].get("answer", raw)
                elif "answer" in data:
                    patch = data["answer"]
        except Exception:
            pass  # use raw if parsing fails

        # normalise escaped newlines
        patch = patch.replace("\\n", "\n")

        verification = verify_patch(
            patch,
            task_id=str(state.metadata.get("instance_id", ""))
        )
        score_value = 1 if verification["overall_passed"] else 0
        explanation = (
            f"Patch valid: {verification['is_patch']} | "
            f"Bandit passed: {verification['bandit_result'].get('passed', True)} | "
            f"Lines added: {verification.get('lines_added', 0)}"
        )
        return Score(
            value=score_value,
            answer=patch,
            explanation=explanation
        )
    return score


# ── Simple pass-through scorer ────────────────────────────────
# @scorer(metrics=[accuracy(), stderr()])
# def record_output():
#     async def score(state, target):
        
#         patch = state.output.completion

#         # run the verifier on the patch to get a score

#         verification = verify_patch(patch, task_id=str(state.metadata.get("instance_id", "")))
        
#         #score 1 if overall passed, else 0

#         score_value = 1 if verification["overall_passed"] else 0

#         explanation=(
#                 f"Patch valid: {verification['is_patch']} | "
#                 f"Bandit passed: {verification['bandit_result'].get('passed', True)} | "
#                 f"Lines added: {verification.get('lines_added', 0)}"
#             )

#         return Score(
#             value=score_value,
#             answer=patch,
#             explanation=explanation
#         )

#     return score




#  Defineing the Inspect Task 
# @task
# def swe_bench_task():
#     return Task(
#         dataset=load_swe_bench_lite(n=1),
#         #solver=coding_agent(),
#         solver=[
#             system_message(
#                 "You are an expert software engineer. "
#                 "You will be given relevant code context followed by an issue. "
#                 "Analyse the context and issue carefully. "
#                 "Output ONLY a git diff patch. No explanation. No preamble. "
#                 "Respond with ONLY the code patch."
#             ),
#             generate()
#         ],

#         #solver=react(
#         #    prompt="You are an expert software engineer. "
#          #          "Analyse the issue carefully, read relevant "
#           #         "code, and produce a minimal correct fix.",
#            # tools=[bash(), python()],
#            # tools=[],
#             #attempts=2,
#         #),
#         scorer=record_output(),
#     )


@task
def swe_bench_task():
    return Task(
        dataset=load_swe_bench_lite(n=1),
        solver=coding_agent(),
        scorer=record_output(),
        approval=get_crm_approval(),
        sandbox="docker",  # Enable sandboxing for tool calls
    )

if __name__ == "__main__":
    # Model options 
    MODEL = "ollama/qwen2.5-coder:7b"       
    

    print(f"Running SWE-bench Lite task with {MODEL}...")
    results = eval(
        swe_bench_task(),
        model=MODEL,
        log_dir="./results",
        max_tokens=2048,  
        timeout=600,    
    )
    print(f"\nDone. Check ./results/ for traces.")
    print(f"Tasks completed: {len(results)}")
