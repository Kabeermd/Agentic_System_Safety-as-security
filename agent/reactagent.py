from datasets import load_dataset
from inspect_ai import Task, task, eval
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.solver import generate, system_message
from inspect_ai.agent import Agent, agent, react
from inspect_ai.tool import bash, python
from inspect_ai.scorer import exact,scorer, Score, accuracy, stderr
from dotenv import load_dotenv
import os

load_dotenv()

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
        samples.append(
            Sample(
                id=task_data["instance_id"],
                input=task_data["problem_statement"],
                metadata={
                    "repo":        task_data["repo"],
                    "base_commit": task_data["base_commit"],
                    "instance_id": task_data["instance_id"],
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


# ── Simple pass-through scorer ────────────────────────────────
@scorer(metrics=[accuracy(), stderr()])
def record_output():
    async def score(state, target):
        # just record the output — no comparison needed yet
        return Score(
            value=1,
            answer=state.output.completion,
            explanation="Output recorded for trace analysis"
        )
    return score

#  Defineing the Inspect Task 
@task
def swe_bench_task():
    return Task(
        dataset=load_swe_bench_lite(n=1),
        #solver=coding_agent(),
        solver=[
            system_message(
                "You are an expert software engineer. "
                "Analyse the issue and produce a minimal correct fix. "
                "Respond with ONLY the code patch — no explanations."
            ),
            generate()
        ],

        #solver=react(
        #    prompt="You are an expert software engineer. "
         #          "Analyse the issue carefully, read relevant "
          #         "code, and produce a minimal correct fix.",
           # tools=[bash(), python()],
           # tools=[],
            #attempts=2,
        #),
        scorer=record_output(),
    )


if __name__ == "__main__":
    # Model options — uncomment the one you want to use
    MODEL = "ollama/qwen2.5-coder:7b"       
    

    print(f"Running SWE-bench Lite task with {MODEL}...")
    results = eval(
        swe_bench_task(),
        model=MODEL,
        log_dir="./results",
        max_tokens=4096,
        timeout=300,
    )
    print(f"\nDone. Check ./results/ for traces.")
    print(f"Tasks completed: {len(results)}")