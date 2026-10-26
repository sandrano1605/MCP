"""Continuous improvement: capture recurring operational faults without auto patching.

An incident may be marked resolved only after a dedicated regression test and
a verified release have been recorded by the operator. Never claim automatic
fixes merely from a healthy status reading.
"""
from __future__ import annotations
import collections
import json
from control_plane import Plane, Refused

PLAYBOOK = {
 "DOM_UNAVAILABLE":{"diagnosis":"Inspect Qt renderer and DOM freshness",
                     "test":"test_dom_loss_no_duplicate_send",
                     "policy":"Pause, preserve turn; do not Retry"},
 "TIMEOUT_UNCONFIRMED":{"diagnosis":"Reconcile delivery journal with last owned chat turn",
                     "test":"test_uncertain_transport_never_reposts",
                     "policy":"No resend without owned finalized checkpoint"},
 "DRAFT_CHANGED":{"diagnosis":"Compare draft hash and original owner",
                     "test":"test_draft_preserved_no_automatic_overwrite",
                     "policy":"Preserve user's draft"},
 "CONTEXT_LIMIT":{"diagnosis":"Verify same project and checkpoint for rollover",
                     "test":"test_project_identity_before_rollover",
                     "policy":"No automatic handoff to another project"},
 "RATE_LIMIT":{"diagnosis":"Check rate limit UI and response state",
                     "test":"test_rate_limit_backoff_no_resend",
                     "policy":"Cooldown then read-only check"},
 "LOGIN_REQUIRED":{"diagnosis":"Check genuine session/login and editor",
                     "test":"test_login_required_blocks_send",
                     "policy":"No permission bypass"},
 "RESPONSE_UNVERIFIED":{"diagnosis":"Compare last assistant timestamp, final marker and run id",
                     "test":"test_false_finalization_blocks_send",
                     "policy":"Do not mark DONE"},
 "RENDERER_MISSING":{"diagnosis":"Inspect WebEngine PID/heartbeat and safe relaunch gates",
                     "test":"test_renderer_missing_no_duplicate",
                     "policy":"No destructive restart of live agents"}
}

def report(plane=None):
    cp=plane or Plane()
    path=cp.issues_file
    counts=collections.Counter()
    last={}
    if path.exists():
        for line in path.read_text(encoding="utf8").splitlines():
            try:item=json.loads(line)
            except ValueError:continue
            typ=item.get("code","OTHER")
            counts[typ]+=1
            last[typ]=max(last.get(typ,0),item.get("at",0))
    rows=[]
    for kind,count in counts.most_common():
        guide=PLAYBOOK.get(kind,{"diagnosis":"Manual triage","test":"test_unclassified_issue",
                                 "policy":"Fail closed"})
        rows.append({"code":kind,"occurrences":count,
                    "priority":"HIGH" if count>=3 else "NORMAL",
                    "diagnosis":guide["diagnosis"],"regression_test":guide["test"],
                    "policy":guide["policy"],"last_at":last[kind]})
    return {"total_incidents":sum(counts.values()),"repeated":sum(n>=3 for n in counts.values()),
            "recommendations":rows,"auto_code_changes":False}
