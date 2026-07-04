import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from inspect_ai.approval import Approval, Approver, ApprovalDecision, ApprovalPolicy, approver
from inspect_ai.tool import ToolCall,ToolCallView
from inspect_ai.model import ChatMessage
from crm.monitor import ConstitutionalRuntimeMonitor, ALLOW, BLOCK

@approver
def crm_approver(
    
    policy_path: str = "crm/policies/coding_policy.md",
    log_path: str = "monitoring/crm_decisions.jsonl"
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
        # check with CRM
        result = crm.check(
            tool_name=call.function,
            tool_args=call.arguments if isinstance(call.arguments, dict) 
                      else {"args": str(call.arguments)},
            task_context=context
        )

        decision = result["decision"]
        reason = result["reason"]

        print(f"\n[CRM] Tool: {call.function}")
        print(f"[CRM] Decision: {decision} — {reason}")

        if decision == ALLOW:
            return Approval(decision="approve", explanation=reason)
        elif decision == BLOCK:
            return Approval(decision="reject", explanation=reason)
        else:
            # AMBER — escalate to human
            print(f"[CRM]  AMBER — Human review required")
            return Approval(decision="escalate", explanation=reason)
        
    return approve

def get_crm_approval(
        policy_path: str = "crm/policies/coding_policy.md",
        log_path: str = "monitoring/crm_decisions.jsonl"

) -> list:
    """ Returns approval policy list for inspect task(approval = list of approvers).
    applies CRM to all tool calls(*)"""

    print("[CRM] Approval policy initialised")

    return [
        ApprovalPolicy(
            approver=crm_approver(
                policy_path=policy_path,
                log_path=log_path
                ),
                tools=["*"]  # Apply CRM to all tool calls
                )
            ]