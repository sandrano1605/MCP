"""V5.7.6 SOLO/Sígueme recovery decision contract (read-only, pure).

This is a release candidate specification, NOT an automatic browser sender.
All actions are advisory. Actual state changes must pass a separate verified
two-stage approval and be checked after acceptance.
"""
from __future__ import annotations
import json
import re
from dataclasses import asdict, dataclass

UNCERTAIN_PHASES={
    "WAITING_SAFE_WORK", "ACK_UNCERTAIN", "SEND_UNCONFIRMED",
    "SENDING", "SOLO_COOLDOWN",
}
UNCERTAIN_MARKERS=(
    "UNCONFIRMED", "UNCERTAIN", "DELIVERY_UNKNOWN",
    "RESPONSE_TIMEOUT", "DOM_UNAVAILABLE",
)
FINAL_DB_STATES={"TIME_LIMIT","SEND_LIMIT","MANUAL_STOP",
                 "DECLARED_DONE_WITH_EVIDENCE"}

@dataclass(frozen=True)
class Decision:
    action: str
    reason: str
    safe_to_resend: bool=False
    can_prepare_restore: bool=False
    can_prepare_start: bool=False
    next_gate: str=""

    def export(self)->dict:
        return asdict(self)

def verified_checkpoint(text:str,run_id:str)->dict|None:
    """Only accept the fenced, matching JSON; never infer from loose prose."""
    if not run_id or not text:return None
    fence=re.escape(chr(96)*3)
    pattern=fence+r"task-state[ \t]*\r?\n([\s\S]*?)\r?\n"+fence
    blocks=re.findall(pattern,text,re.IGNORECASE)
    if not blocks:return None
    try:
        obj=json.loads(blocks[-1])
    except (ValueError,TypeError):return None
    if (not isinstance(obj,dict) or obj.get("run_id")!=run_id
            or obj.get("status") not in ("working","done","needs_user")
            or not isinstance(obj.get("pending"),list)
            or not isinstance(obj.get("completed"),list)
            or not isinstance(obj.get("evidence"),list)):
        return None
    return obj

def decide(*,agent_id:int,controller:dict,dom:dict|None,
           db_state:str|None=None,checkpoint:dict|None=None,
           saved:dict|None=None,project_matches:bool=True)->dict:
    """Read-only next gate for 1..6, applying most restrictive evidence first."""
    if not isinstance(agent_id,int) or agent_id not in range(1,7):
        raise ValueError("agent_id must be 1..6")
    a=controller or {}
    if a.get("mounted") is False:
        return Decision("MOUNT_PANEL","No panel mounted",
                        next_gate="Approve layout change, then verify panel identity").export()
    if not isinstance(dom,dict) or not dom.get("url") or dom.get("ready") is not True:
        return Decision("RESTORE_READABILITY","Live DOM/editor or URL not verified",
                        next_gate="Observe authenticated chat; do not navigate blindly").export()
    if not project_matches:
        return Decision("PROJECT_MISMATCH","Task project and opened chat disagree",
                        next_gate="Select correct project chat with explicit assignment").export()
    if dom.get("isGenerating") or a.get("generating"):
        return Decision("OBSERVE_STREAM","ChatGPT may still be generating",
                        next_gate="Wait for a finalized owned reply; no resend").export()
    if a.get("transport_pending") or int(a.get("queue") or 0)>0:
        return Decision("RECONCILE_DELIVERY","Transport still pending/queued",
                        next_gate="Inspect transport ledger and last owned turn").export()
    if dom.get("draft"):
        return Decision("PRESERVE_DRAFT","Existing editor text may be an unsent or duplicated instruction",
                        next_gate="Compare saved draft fingerprint with user turn and delivery ledger; never erase or click Retry").export()
    if (dom.get("blocked") or dom.get("responseLoadFailed") or dom.get("deliveryTimeout")
        or dom.get("interrupted") or dom.get("rateLimit") or dom.get("contextLimit")
        or "unknown error" in str(dom.get("alerts") or "").lower()):
        return Decision("RECONCILE_ERROR","Visible ChatGPT error, limit or incomplete reply",
                        next_gate="One read-only reconciliation. A controlled single reload requires snapshot; no resend").export()
    failed=str(a.get("transport_failed") or "")
    if failed and any(x in failed.upper() for x in UNCERTAIN_MARKERS):
        return Decision("RECONCILE_UNCERTAIN","Transport has uncertain delivery even if the GUI appears healthy",
                        next_gate="Match owner, turn, checkpoint and send ledger; no second POST").export()
    if failed:
        return Decision("TRANSPORT_ERROR","Transport failure needs classification",
                        next_gate="Diagnose error class before new sends").export()
    rid=str(a.get("run_id") or "")
    cp=checkpoint if isinstance(checkpoint,dict) else None
    owned=bool(dom.get("lastAssistantAfterLastUser")) and rid and rid in str(dom.get("userText") or "")
    complete=bool(cp and cp.get("run_id")==rid and cp.get("status")=="done"
                  and cp.get("pending")==[] and cp.get("evidence"))
    if complete and owned and bool(dom.get("finalized")):
        return Decision("VERIFY_DONE","Completion is asserted by an owned final checkpoint",
                        next_gate="Confirm DB terminal state and evidence before marking DONE").export()
    if a.get("active"):
        phase=str(a.get("phase") or "")
        if phase.startswith("ROLLOVER"):
            return Decision("VERIFY_ROLLOVER","Controller awaiting correct project/editor",
                            next_gate="New chat must be in same project, empty and authenticated").export()
        if phase=="WAITING_SAFE_WORK" or phase in UNCERTAIN_PHASES:
            return Decision("RECONCILE_CONTROLLER","Controller waiting on previous message/response",
                            next_gate="Match checkpoint and exact last send; do not replay").export()
        return Decision("KEEP_RUNNING","Active controller, no independently verified terminal condition",
                        next_gate="Monitor progress and completed evidence without restarting").export()
    if cp and cp.get("status")=="needs_user":
        return Decision("NEEDS_USER","Checkpoint requests indispensable external authorization",
                        next_gate="Continue only independent authorized work").export()
    if (cp and cp.get("run_id")==rid and cp.get("status")=="working"
        and bool(cp.get("safe_next_steps")) and bool(cp.get("evidence"))
        and dom.get("finalized") and owned and
        db_state in ("RUNNING","WAITING_SAFE_WORK") and
        saved and saved.get("active") and
        saved.get("run_id")==rid and saved.get("expected_url")==dom.get("url")):
        return Decision("PREPARE_SAME_RUN_RESTORE","All final-owned checkpoint and saved identity guards satisfied",
                        can_prepare_restore=True,
                        next_gate="Stage resume, approve once, compare run_id and iteration after API ACK").export()
    if db_state in FINAL_DB_STATES and cp and cp.get("status")=="working" and bool(cp.get("safe_next_steps")):
        return Decision("PREPARE_CONTEXTUAL_START","Earlier controller is terminal; remaining work needs a new run",
                        can_prepare_start=True,
                        next_gate="Confirm project assignment, backup, approval and new run id").export()
    return Decision("RECONCILE_PREVIOUS_RUN","No certified safe transition or checkpoint",
                    next_gate="Audit last user, assistant, ledger and local task memory").export()
