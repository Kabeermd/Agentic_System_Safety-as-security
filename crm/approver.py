"""MAIN CRM APPROVER WRAPPER FOR BOTH SWE-BENCH LITE AND REDCODE-EXEC TASKS

This Script wraps the Constitutional Runtime Monitor (CRM) as an @approver for Inspect tasks. 

CRM(Control Runtime Monitoring) :- 

The CRM is a tool-agnostic, policy-driven approver that evaluates tool calls against a specified policy and logs decisions. It can operate in different modes (log-only, enforced, human-gated) depending on the task configuration.
The CRM approver is designed to be integrated into Inspect tasks, allowing for automated approval, rejection
, or escalation of tool calls based on the defined policy. It supports multiple run configurations for different evaluation scenarios, including capability benchmarks, enforcement runs, and human-gated demonstrations.
The approver extracts context from the task history, resolves instance identifiers, and interacts with the CRM to determine the appropriate action for each tool call. It provides detailed logging and decision-making transparency, making it suitable for both automated and human-in-the-loop evaluation workflows.

"""

import os
import sys
import re
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from inspect_ai.approval import Approval, Approver, ApprovalDecision, ApprovalPolicy, approver, auto_approver
from inspect_ai.tool import ToolCall,ToolCallView
from inspect_ai.model import ChatMessage
from inspect_ai.solver import TaskState 
from inspect_ai.util import store

from inspect_ai.solver._task_state import sample_state
from crm.monitor import ConstitutionalRuntimeMonitor, ALLOW, BLOCK

@approver
def crm_approver(
    
    policy_path: str = "crm/policies/coding_policy.md",
    log_path: str = "monitoring/crm_decisions.jsonl",
    enforce: bool = False  # False = log-only (capability); True = block (RedCode)
) -> Approver:
    
    """Crm wrapped as inspect @approver.
    This allows it to be easily integrated into any inspect task.
    called before ever tool excecution, and can approve/block/escalate based on policy."""

    crm = ConstitutionalRuntimeMonitor(policy_path=policy_path, log_path=log_path)

    async def approve(
        message: str,
        call: ToolCall,
        view: ToolCallView,
        history: list[ChatMessage],
    ) -> Approval:
        
        print(f"\n[CRM] Evaluating tool call: {call.function} with args {call.arguments}")

        # get task context from last user message in history
        context = ""
        for msg in reversed(history):
            if hasattr(msg, "role") and msg.role == "user":
                context = str(msg.content)[:500]
                break

        # extract instance_id from the task state
        # Resolve instance_id from the marker the loader stamps into the input.
        # history is passed directly to this callback, so it survives the subtask
        # context-isolation that makes store()/sample_state() come back empty here.
        instance_id = "unknown"
        for msg in history:
            m = re.search(r"\[CRM-INSTANCE:\s*([^\]]+)\]", str(getattr(msg, "content", "")))
            if m:
                instance_id = m.group(1).strip()
                break
        print(f"[CRM][id] resolved instance_id={instance_id!r} for tool={call.function}")
        # check with CRM
        result = crm.check(
            tool_name=call.function,
            tool_args=call.arguments if isinstance(call.arguments, dict) 
                      else {"args": str(call.arguments)},
            task_context=context,
            instance_id=instance_id # type: ignore
        )

        decision = result["decision"]
        reason = result["reason"]

        print(f"\n[CRM] Tool: {call.function}")
        print(f"[CRM] Decision: {decision} — {reason}")

        if decision == ALLOW:
            return Approval(decision="approve", explanation=reason)
        elif decision == BLOCK:
            # LOG-ONLY MODE: decision is recorded in crm_decisions.jsonl via crm.check(),
            # but not enforced during capability benchmarks (SWE-bench/SaV-Bench) to avoid
            # perturbing agent trajectories. Enforcement is enabled separately for RedCode-Exec.
            # print(f"[CRM] BLOCK (log-only) — would have blocked: {reason}")
            # return Approval(decision="approve", explanation=reason)# for log-only mode, we approve but log the block reason but do not enforce it. This is to avoid perturbing agent trajectories during capability benchmarks (SWE-bench/SaV-Bench). Enforcement is enabled separately for RedCode-Exec. when we want to enforce blocking, we can change this to return Approval(decision="reject", explanation=reason)
            if enforce:
                # ENFORCEMENT MODE (RedCode-Exec): actually stop the tool call.
                print(f"[CRM] BLOCK (enforced) — rejecting: {reason}")
                return Approval(decision="reject", explanation=reason)
            else:
                # LOG-ONLY (SWE-bench/SaV-Bench): record but don't perturb trajectory.
                print(f"[CRM] BLOCK (log-only) — would have blocked: {reason}")
                return Approval(decision="approve", explanation=reason)
        
        else:  # AMBER — overseer uncertain
            if enforce:
                # ENFORCEMENT (RedCode-Exec): uncertainty on a deliberately-risky
                # prompt is treated as a risk. Reject, so the run stays autonomous
                # (no escalate = no stall, no human in the loop contaminating the
                # block-rate). Under enforcement: BLOCK and AMBER both reject;
                # only ALLOW proceeds.
                print(f"[CRM] AMBER (enforced as block) — rejecting: {reason}")
                return Approval(decision="reject", explanation=reason)
            # LOG-ONLY: escalate to Tier-2 (auto or human) as before.
            print(f"[CRM] AMBER — escalate to Tier-2")
            return Approval(decision="escalate", explanation=reason)
        
    return approve

def get_crm_approval(
        policy_path: str = "crm/policies/coding_policy.md",
        log_path: str = "monitoring/crm_decisions.jsonl",
        enforce: bool = False,
        tier2: str = "auto",     # "auto" | "human" | "none"
) -> list:
    """Approval policy list for an Inspect task. The CRM is always Tier 1;
    Tier 2 handles AMBER escalations and varies by run type.

    Three run configurations:

    CAPABILITY (enforce=False, tier2="auto") — SWE-bench / SaV-Bench:
        CRM BLOCK is log-only (downgraded to approve). AMBER -> escalate ->
        auto_approver approves it (logged) so unattended batches don't stall.

    ENFORCEMENT (enforce=True, tier2="none") — RedCode-Exec:
        CRM BLOCK -> reject; AMBER -> reject (see approver). CRM is the SOLE
        approver — NO Tier-2, because any auto-approve fallback would override
        a reject and fabricate the block-rate. Fully autonomous, clean number.

    HUMAN GATE (enforce=False, tier2="human") — AMBER-gate demonstration:
        AMBER -> escalate -> human_approver pauses the run for a live decision.
        Small, deliberate N only — a human in a large batch both stalls the run
        and contaminates any measured rate.
    """
    print(f"[CRM] Approval initialised (enforce={enforce}, tier2={tier2})")

    if enforce and tier2 != "none":
        raise ValueError("enforce=True requires tier2='none' — a Tier-2 approver "
                         "would override CRM rejects and fabricate the block-rate.")

    policies = [
        ApprovalPolicy(
            approver=crm_approver(policy_path=policy_path, log_path=log_path, enforce=enforce),
            tools=["*"],
        ),
    ]

    if tier2 == "auto":
        policies.append(ApprovalPolicy(approver=auto_approver(decision="approve"), tools=["*"]))
    elif tier2 == "human":
        from inspect_ai.approval import human_approver
        policies.append(ApprovalPolicy(approver=human_approver(), tools=["*"]))
    elif tier2 == "none":
        pass  # enforcement: CRM reject is final, no fallback
    else:
        raise ValueError(f"tier2 must be 'auto'|'human'|'none', got {tier2!r}")

    return policies