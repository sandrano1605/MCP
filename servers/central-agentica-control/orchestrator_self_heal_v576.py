"""Policy-only supervisor for ChatGPT Orchestrator panel #7.

The supervisor is Python code, not the ChatGPT model it supervises.
It cannot send prompts, click Retry, reset workers or bypass authentication.
The caller persists an intent BEFORE a single recovery action.
"""
from __future__ import annotations
from dataclasses import dataclass,asdict
import hashlib,json

MAX_RECOVERIES_PER_EPISODE=2
RECOVERY_COOLDOWN_SECONDS=90
STALLED_SECONDS=480

@dataclass(frozen=True)
class Decision:
    action:str
    reason:str
    requires_user:bool=False
    restart_allowed:bool=False
    def export(self):
        return asdict(self)

def fingerprint(project,chat_url,error,run_epoch):
    return hashlib.sha256(json.dumps(
        [str(project),str(chat_url),str(error),str(run_epoch)],
        ensure_ascii=False).encode("utf8")).hexdigest()

def diagnose(*,enabled:bool,project_valid:bool,project_matches:bool,
             state:dict|None,transport:dict|None,now:float,
             recovery:dict|None=None,bootstrap_stage:str="UNSTARTED",
             progress_at:float|None=None)->dict:
    """Classify before actions. Never restart while a send may still be active."""
    if not enabled:
        return Decision("DISABLED","User turned off coordinator").export()
    if not project_valid:
        return Decision("NEEDS_USER","Orchestrator project URL is not configured",
                        requires_user=True).export()
    s=state or {}
    t=transport or {}
    if not s.get("url") or not s.get("ready"):
        # Authenticated editor not yet verified: wait; no blind resend.
        if s.get("loginRequired") or s.get("authRequired"):
            return Decision("NEEDS_USER","ChatGPT requires authentication",
                            requires_user=True).export()
        if (s.get("url") and project_matches and progress_at and
                now-progress_at>=STALLED_SECONDS and
                not (t.get("active") or t.get("pending") or t.get("queue"))):
            attempts=int((recovery or {}).get("attempts") or 0)
            if attempts>=MAX_RECOVERIES_PER_EPISODE:
                return Decision("NEEDS_USER","Coordinator editor stalled after recovery budget",
                                requires_user=True).export()
            if now-float((recovery or {}).get("last_attempt_at") or 0)>=RECOVERY_COOLDOWN_SECONDS:
                return Decision("RECOVER_COORDINATOR_CHAT","Authenticated project editor stalled",
                                restart_allowed=True).export()
        return Decision("WAIT_EDITOR","Project/editor not ready").export()
    if not project_matches:
        return Decision("NEEDS_USER","Chat is outside the configured project",
                        requires_user=True).export()
    if (t.get("active") or t.get("pending") or t.get("queue") or
            s.get("isGenerating")):
        if progress_at and now-progress_at>=STALLED_SECONDS:
            return Decision("RECONCILE_INFLIGHT","Long-running response: confirm delivery first").export()
        return Decision("OBSERVE_INFLIGHT","ChatGPT is responding or delivery is pending").export()
    if bootstrap_stage in ("CLAIMED","UNCERTAIN") or t.get("failed"):
        # A failed message is never proof that it wasn't delivered.
        return Decision("RECONCILE_DELIVERY","Unconfirmed outgoing coordinator message").export()
    if s.get("draft"):
        return Decision("PRESERVE_DRAFT","Editor contains a draft; snapshot and reconcile before reset").export()
    error=bool(s.get("blocked") or s.get("interrupted") or
               s.get("responseLoadFailed") or s.get("deliveryTimeout") or
               "unknown error" in str(s.get("alerts") or "").lower())
    if s.get("rateLimit"):
        return Decision("WAIT_RATE_LIMIT","Do not bypass ChatGPT usage limits").export()
    if s.get("contextLimit"):
        return Decision("PREPARE_PROJECT_ROLLOVER","Conversation reached context limit",
                        restart_allowed=True).export()
    if not error:
        return Decision("LISTENING","Healthy: wait for events").export()
    recovery=recovery or {}
    attempts=int(recovery.get("attempts") or 0)
    if attempts>=MAX_RECOVERIES_PER_EPISODE:
        return Decision("NEEDS_USER","Repeated error after recovery budget exhausted",
                        requires_user=True).export()
    if now-float(recovery.get("last_attempt_at") or 0)<RECOVERY_COOLDOWN_SECONDS:
        return Decision("COOLDOWN","Controlled recovery already attempted").export()
    return Decision("RECOVER_COORDINATOR_CHAT","Verified ChatGPT UI error; recover coordinator only",
                    restart_allowed=True).export()
