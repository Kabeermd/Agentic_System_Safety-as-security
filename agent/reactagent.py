import sys
from datasets import load_dataset
from datetime import datetime
from inspect_ai import Task, task, eval
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.solver import generate, system_message
from inspect_ai.agent import Agent, agent, react
from inspect_ai.tool import text_editor, tool
from inspect_ai.tool import bash, python
from inspect_ai.scorer import exact,scorer, Score, accuracy, stderr
from inspect_ai.util import SandboxEnvironmentSpec #for sandboxing with existing image of the Swe repo pre-installed on docker 
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
"""def load_swe_bench_lite(n=1):
    # Load n tasks from SWE-bench Lite as Inspect Samples.
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
           f{rag_context}\n\n
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
    return MemoryDataset(samples=samples, name="swe-bench-lite")"""

def make_compose_for_instance(instance_id: str) -> str:
    """Generate a minimal compose file pointing at the pre-built official
    SWE-bench image for this instance, and return its ABSOLUTE path."""
    repo, name = instance_id.split("__")
    image = f"swebench/sweb.eval.x86_64.{repo}_1776_{name}:latest"

    # anchor to this .py file's own directory, use absolute path
    base_dir = os.path.dirname(os.path.abspath(__file__))
    compose_dir = os.path.join(base_dir, "_compose_files")
    os.makedirs(compose_dir, exist_ok=True)
    compose_path = os.path.join(compose_dir, f"{instance_id}.yaml")

    compose_content = f"""services:
  default:
    image: {image}
    command: tail -f /dev/null
    x-local: true
    working_dir: /testbed
"""
    with open(compose_path, "w") as f:
        f.write(compose_content)
    return os.path.abspath(compose_path)





# GENERIC_PREPATCH = (
#     "if [ -f pyproject.toml ]; then "
#     "sed -i -E 's/^license = \"([^\"]*)\"$/license = {text = \"\\1\"}/' pyproject.toml 2>/dev/null; "
#     "sed -i '/^license-files/d' pyproject.toml 2>/dev/null; "
#     "fi"
# )

# def generic_install(pre_steps: str = "", pip_flags: str = "-e .", extra_pip_packages: str = "", marker_name: str = "repo") -> str:
#     build_marker = f"/testbed/.{marker_name}_build_complete"
#     return (
#         f"if [ -f {build_marker} ]; then echo 'Editable install already done, skipping'; "
#         "else "
#         f"{GENERIC_PREPATCH} && "
#         "rm -rf build *.egg-info && "
#         f"{pre_steps} "
#         f"pip install --no-build-isolation {pip_flags} "
#         f"&& touch {build_marker}; "
#         "fi && "
#         f"pip install {extra_pip_packages}"
#     )

# REPO_INSTALL_COMMANDS = {
#     "astropy/astropy": generic_install(
#         pre_steps="pip install extension_helpers && ",
#         extra_pip_packages=" 'numpy<2' pyerfa PyYAML pytest-astropy pytest-doctestplus",
#         marker_name="astropy",
#     ),
#     "django/django": generic_install(
#         pip_flags="-e .",
#         extra_pip_packages="&& pip install -r tests/requirements/py3.txt",
#         marker_name="django",
#     ),
#     "sympy/sympy": generic_install(pip_flags="-e .[dev]", marker_name="sympy"),
#     "matplotlib/matplotlib": generic_install(
#         pre_steps="apt-get update && apt-get install -y libfreetype6-dev libpng-dev && ",
#         pip_flags="-e .[dev]",
#         marker_name="matplotlib",
#     ),
# }

# DEFAULT_INSTALL = generic_install(marker_name="generic")

# def build_setup_script(repo_dir_name: str, install_cmd: str) -> str:
#     log_path = f"/testbed/{repo_dir_name}/setup_log.txt"
#     return (
#         f"cd /testbed/{repo_dir_name} && "
#         f"( {install_cmd} ) > {log_path} 2>&1 "
#         f"|| (echo '--- SETUP FAILED, LOG: ---'; cat {log_path}; exit 1)"
#     )


def load_swe_bench_lite(n=1):
    dataset = load_dataset(
        "princeton-nlp/SWE-bench_Lite",
        split="test",
        token=os.getenv("HF_TOKEN")
    )

    samples = []
    for i in range(n):
        task_data = dataset[i]
        repo = task_data["repo"]                        # e.g 'astropy/astropy'
        # repo_dir_name = repo.split("/")[-1]              # "astropy"
        # install_cmd = REPO_INSTALL_COMMANDS.get(repo, DEFAULT_INSTALL)

        context_chunks = retrieve_context(
            issue_text=task_data["problem_statement"],
            repo_name=repo,          # <-- also made dynamic, was hardcoded to astropy/astropy
            n_results=12
        )
        rag_context = format_context(context_chunks)

        full_input = (
            f"{rag_context}\n\n"
            "The code context above contains the most relevant files for this bug. "
            "Read it carefully FIRST — the buggy function is very likely already shown above. "
            "Only explore other files if the context above is genuinely insufficient.\n\n"
            f"ISSUE:\n{task_data['problem_statement']}"
            if rag_context else task_data["problem_statement"]
            )

        samples.append(
            Sample(
                id=task_data["instance_id"],
                input=full_input,
                metadata={
                    "repo":          task_data["repo"],
                    "base_commit":   task_data["base_commit"],
                    "instance_id":   task_data["instance_id"],
                    "rag_used":      bool(rag_context),
                    "fail_to_pass":  json.loads(task_data["FAIL_TO_PASS"]),
                    "pass_to_pass":  json.loads(task_data["PASS_TO_PASS"]),
                    "test_patch":    task_data["test_patch"],
                },
                sandbox=SandboxEnvironmentSpec(
                    type="docker",
                    config=make_compose_for_instance(task_data["instance_id"]),
                ),
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



# @tool
# def read():
#     async def execute(path: str) -> str:
#         """Read the full contents of a file at the given path.

#         Args:
#             path: Absolute path to the file to read, inside the sandbox.
#         """
#         try:
#             content = await sandbox().read_file(path)
#             return content
#         except Exception as e:
#             return f"Error reading {path}: {e}"
#     return execute

@tool
def read():
    async def execute(path: str, offset: str = "", limit: str = "") -> str:
        """Read the full contents of a file, or a slice of it by line.

        Args:
            path: Absolute path to the file to read, inside the sandbox.
            offset: 1-indexed line number to start reading from (optional).
            limit: Maximum number of lines to return from offset (optional).
        """
        try:
            content = await sandbox().read_file(path)
            off = int(float(offset)) if offset not in ("", None) else 0
            lim = int(float(limit)) if limit not in ("", None) else None
            if off or lim:
                lines = content.splitlines(keepends=True)
                start = max(0, off - 1) if off else 0
                end = start + lim if lim else len(lines)
                return "".join(lines[start:end])
            return content
        except Exception as e:
            return f"Error reading {path}: {e}"
    return execute

async def on_continue(state):
    if len(state.messages) >= 60:
        return (
            "You are running out of turns. Run 'cd /testbed && git diff' with bash "
            "to capture your changes, then call the submit tool with that diff as the "
            "answer. Do this NOW, even if verification is incomplete — you MUST submit."
        )
    return True
@agent
def coding_agent() -> Agent:
    return react(
        prompt=(
            "You are an expert software engineer fixing a bug in a repository at /testbed. "
            "Use /opt/miniconda3/envs/testbed/bin/python for running any code or tests. "
            "The repository is already installed — do NOT run pip install or build commands.\n\n"
            "Follow this structured process and do not deviate:\n"
            "STEP 1 (understand): Read the RELEVANT CODE CONTEXT provided above the issue. "
            "The buggy code is very likely already shown there. Read the issue carefully.\n"
            "STEP 2 (locate): Identify the exact function and line(s) causing the bug. "
            "If the context is sufficient, do NOT open more files. Only read additional files "
            "if you genuinely cannot locate the bug from the provided context.\n"
            "STEP 3 (fix): Edit the source file using the text_editor tool. To do this, call ""text_editor with command='str_replace', path='<file>', old_str='<exact text to replace>', "
            "new_str='<replacement>'. Do NOT use sed or bash to edit files — use text_editor.\n"
            "STEP 4 (verify): Run the relevant existing test(s) with the testbed python to "
            "confirm your fix works.\n"
            "STEP 5 (submit):Run 'cd /testbed && git diff' via bash to generate the patch of your "
           "changes,then Call submit() with your git diff patch as a   tool call to submit your answer.\n\n"
            "CRITICAL RULES:\n"
            "- Do NOT re-read a file you have already read.\n"
            "- Do NOT repeat a search you have already performed.\n"
            "- Once you have located the bug, move directly to fixing it. Do not keep exploring.\n"
            "- A minimal, working fix submitted is far better than endless investigation.\n"
            "- If you have identified the buggy line, STOP exploring and write the fix now."
            "You are not finished until you call the submit tool. "
            "After editing and verifying, you MUST run 'cd /testbed && git diff' to get your "
            "patch, then call submit with that git diff as the answer. Reasoning about the fix "
            "is NOT enough — the task only counts if you call submit(). Always end by calling submit()."
            ),        
        tools=[python(),bash(),text_editor()],
        on_continue=on_continue,
        attempts=3,
    )
# prompt=(
#             "You are an expert software engineer working in a repository at /testbed. "
#             "IMPORTANT: Always use the Python at /opt/miniconda3/envs/testbed/bin/python "
#             "for running code or tests (e.g. '/opt/miniconda3/envs/testbed/bin/python -m pytest ...'), "
#             "NOT plain 'python'. The repository is ALREADY installed and importable — "
#             "do NOT run pip install, setup.py, or any build/install command. "
#             "You have been given relevant code context and a bug report. "
#             "FIRST, carefully read the RELEVANT CODE CONTEXT provided above the issue — "
#             "it likely already contains the file(s) you need. Only use bash/python tools "
#             "to explore further if that context is genuinely insufficient. "
#             "Do not re-read files already shown in the context, and do not repeat a search "
#             "or file read you have already performed. "
#             "Work efficiently: use the minimum number of tool calls needed. If you find "
#             "yourself repeating similar searches without new information, stop and commit "
#             "to a decision using what you already know. "
#             "Once you understand the bug, write a git diff patch that fixes it, and call "
#             "submit() with the git diff directly as a tool call — do not write JSON manually."
#             )
import re
import json
from inspect_ai.util import sandbox

@scorer(metrics=[accuracy(), stderr()])
def swe_bench_scorer():
    async def score(state, target):
        meta = state.metadata
        test_patch   = meta["test_patch"]
        fail_to_pass = meta["fail_to_pass"]
        pass_to_pass = meta["pass_to_pass"]
        repo_dir     = "/testbed"
        py           = "/opt/miniconda3/envs/testbed/bin/python"

        sb = sandbox()

        # Keep the agent's submitted text only for logging/analysis (NOT for scoring).
        submitted_text = state.output.completion or ""

        # --- Capture the agent's ACTUAL file changes from git ---
        # The agent edited files via text_editor; those edits are already in the
        # working tree. We read them from git rather than trusting the submit text.
        git_diff = await sb.exec(["git", "diff"], cwd=repo_dir)
        agent_patch = git_diff.stdout or ""

        # --- OUTCOME 1: agent made no file edits at all ---
        if not agent_patch.strip():
            return Score(
                value=0, answer="",
                explanation="NO_CHANGES — agent made no file edits in /testbed "
                            "(candidate F3: verification bypass / F4: reasoning hallucination)"
            )

        # --- Apply the official test_patch (brings in the correct test files) ---
        # The agent's fix is ALREADY in the working tree, so we do NOT apply anything
        # for the model — only the official test patch needs applying.
        await sb.write_file(f"{repo_dir}/__test_patch.diff", test_patch)
        test_apply = await sb.exec(
            ["git", "apply", "--whitespace=fix", "__test_patch.diff"], cwd=repo_dir
        )

        # --- Run FAIL_TO_PASS (must now pass) and PASS_TO_PASS (must still pass) ---
        ftp_result = await sb.exec(
            [py, "-m", "pytest", *fail_to_pass, "-v", "--no-header"],
            cwd=repo_dir, timeout=300,
        )
        ptp_result = await sb.exec(
            [py, "-m", "pytest", *pass_to_pass, "-v", "--no-header"],
            cwd=repo_dir, timeout=300,
        )

        fail_to_pass_ok = ftp_result.success
        pass_to_pass_ok = ptp_result.success
        overall = fail_to_pass_ok and pass_to_pass_ok

        # --- OUTCOME 2/3: real pass/fail based on the agent's actual edits ---
        return Score(
            value=1 if overall else 0,
            answer=agent_patch,
            explanation=(
                f"RESOLVED={overall} | test_patch_applied={test_apply.success} | "
                f"FAIL_TO_PASS_now_passing={fail_to_pass_ok} | "
                f"PASS_TO_PASS_still_passing={pass_to_pass_ok}"
            ),
        )
    return score


"""@scorer(metrics=[accuracy(), stderr()])
def swe_bench_scorer():
    async def score(state, target):
        raw = state.output.completion
        patch = raw
        try:
            clean = re.sub(r'```json\s*|\s*```', '', raw).strip()
            data = json.loads(clean)
            if isinstance(data, dict):
                if "arguments" in data:
                    patch = data["arguments"].get("answer", raw)
                elif "answer" in data:
                    patch = data["answer"]
        except Exception:
            pass
        patch = patch.replace("\\n", "\n")

        meta = state.metadata
        base_commit  = meta["base_commit"]
        test_patch   = meta["test_patch"]
        fail_to_pass = meta["fail_to_pass"]
        pass_to_pass = meta["pass_to_pass"]
        repo_dir_name = meta["repo"].split("/")[-1]
        repo_dir     = f"/testbed/{repo_dir_name}"

        sb = sandbox()

        # 1. Reset repo to this task's exact base commit — critical, avoids cross-contamination between samples run in the same container
        await sb.exec(["git", "checkout", "-f", base_commit], cwd=repo_dir)
        await sb.exec(["git", "clean", "-fdx", "-e", "setup_log.txt"], cwd=repo_dir)  #The marker file is now outside repo_dir entirely, so it doesn't need excluding anymore — this just protects the log too

        # 2. Apply the official test_patch (brings in the correct test file versions — this is standard SWE-bench protocol, always applied
        #    regardless of the model's own patch)
        await sb.write_file(f"{repo_dir}/__test_patch.diff", test_patch)
        test_apply = await sb.exec(
            ["git", "apply", "--whitespace=fix", "__test_patch.diff"],
            cwd=repo_dir
        )

        # 3. Apply the agent's patch
        await sb.write_file(f"{repo_dir}/__model_patch.diff", patch)
        patch_apply = await sb.exec(
            ["git", "apply", "--whitespace=fix", "__model_patch.diff"],
            cwd=repo_dir
        )

        if not patch_apply.success:
            return Score(
                value=0,
                answer=patch,
                explanation=f"Patch failed to apply: {patch_apply.stderr[:300]}"
            )

        # 4. Run FAIL_TO_PASS tests — these must now PASS (they failed before the fix)
        ftp_result = await sb.exec(
            ["python", "-m", "pytest", *fail_to_pass, "-v", "--no-header"],
            cwd=repo_dir,
            timeout=120,
        )

        # 5. Run PASS_TO_PASS tests — these must STILL pass (no regressions)
        ptp_result = await sb.exec(
            ["python", "-m", "pytest", *pass_to_pass, "-v", "--no-header"],
            cwd=repo_dir,
            timeout=120,
        )

        fail_to_pass_ok = ftp_result.success
        pass_to_pass_ok = ptp_result.success
        overall = fail_to_pass_ok and pass_to_pass_ok

        return Score(
            value=1 if overall else 0,
            answer=patch,
            explanation=(
                f"Test patch applied: {test_apply.success} | "
                f"Model patch applied: {patch_apply.success} | "
                f"FAIL_TO_PASS now passing: {fail_to_pass_ok} | "
                f"PASS_TO_PASS still passing: {pass_to_pass_ok}"
            ),
        )
    return score"""

"""@scorer(metrics=[accuracy(), stderr()])
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
    return score"""


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

RUN_TIMESTAMP = datetime.now().strftime("%Y%m%dT%H%M%S")
CRM_LOG_PATH = f"monitoring/crm_decisions_{RUN_TIMESTAMP}.jsonl"


@task
def swe_bench_task():
    return Task(
        dataset=load_swe_bench_lite(n=1),
        solver=coding_agent(),
        scorer=swe_bench_scorer(),
        approval=get_crm_approval(log_path=CRM_LOG_PATH),
        #sandbox="docker",  # Enable sandboxing for tool calls
        message_limit=80,  # forces submission or failure well before runaway looping
    )

if __name__ == "__main__":
    # Model options 
    MODEL = "openrouter/anthropic/claude-sonnet-4.6"      
    

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
