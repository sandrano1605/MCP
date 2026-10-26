"""Read-only six-agent supervisor, completion evidence and regression feedback.

Run as an independent AF9328 sidecar. Never sends ChatGPT messages. Monitors
published API and persisted DB; distinguishes done, stalled, partial and unknown.
"""
from __future__ import annotations
import argparse
import json
import os
import sqlite3
import time
from pathlib import Path
from control_plane import Plane, Refused, read_json, write_json, digest

INCIDENT_TYPES = {
    "NOT_MOUNTED":"Use vetted layout=6 tool (preserve current panels)",
    "FAILED_TRANSPORT":"Reconcile last turn/intent before allowing a new send",
    "DOM_STALE":"Inspect renderer and preserve uncertain turn, no Retry",
    "NO_PROGRESS":"Inspect response, rate limit, checkpoint; do not infer failure",
    "TIMEOUT_UNCONFIRMED":"Do not replay the last instruction; reconcile first",
    "LIMIT_REACHED":"Inspect verified checkpoint and plan context rollover",
    "UNVERIFIED_CLOSE":"Task closure requires final checkpoint and evidence"
}
COMPLETED_RUN_STATES = {"DECLARED_DONE_WITH_EVIDENCE"}

class Supervisor:
    def __init__(self,plane=None):
        self.plane=plane or Plane()
        self.last_path=self.plane.state/"last_monitor.json"
        self.events_path=self.plane.state/"supervisor_events.jsonl"

    def _db_summary(self,aid,run_id):
        if not run_id:return {"outcome":"NO_RUN"}
        try:
            with self.plane._db() as db:
                row=db.execute("SELECT state FROM runs WHERE id=?",(run_id,)).fetchone()
                turn=db.execute("SELECT checkpoint FROM turns WHERE run=? AND agent=? "
                    "ORDER BY id DESC LIMIT 1",(run_id,aid)).fetchone()
        except (sqlite3.Error,Refused):
            return {"outcome":"DB_UNAVAILABLE"}
        if not row:return {"outcome":"RUN_MISSING"}
        cp={}
        if turn and turn[0]:
            try:cp=json.loads(turn[0])
            except (TypeError,ValueError):pass
        valid=(isinstance(cp,dict) and cp.get("run_id")==run_id and
               cp.get("status")=="done" and cp.get("pending")==[] and
               bool(cp.get("evidence")))
        state=row[0]
        if valid and state in COMPLETED_RUN_STATES:
            return {"outcome":"DONE_CONFIRMED","evidence_count":len(cp["evidence"]),
                    "db_state":state}
        if state=="NEEDS_USER":return {"outcome":"NEEDS_USER","db_state":state}
        if state in COMPLETED_RUN_STATES and not valid:
            return {"outcome":"UNVERIFIED_CLOSE","db_state":state}
        return {"outcome":"WORKING_OR_STOPPED","db_state":state}

    @staticmethod
    def classify(a,db):
        if not a["mounted"]:return "NOT_MOUNTED"
        if a["transport_failed"]:
            if "UNCONFIRMED" in a["transport_failed"]:return "TIMEOUT_UNCONFIRMED"
            return "FAILED_TRANSPORT"
        if a["dom_age"] is None or a["dom_age"]>180:
            return "DOM_STALE"
        if a["active"] and a["iteration"] is not None and a["max_iterations"] is not None:
            if a["iteration"]>=a["max_iterations"]:return "LIMIT_REACHED"
        if db.get("outcome")=="UNVERIFIED_CLOSE":return "UNVERIFIED_CLOSE"
        if db.get("outcome")=="DONE_CONFIRMED":return "DONE_CONFIRMED"
        if a["active"] and a["health"]=="LENTO":return "NO_PROGRESS"
        if a["active"]:return "ACTIVE"
        return "IDLE"

    def poll(self):
        live=self.plane.status()
        entries={}
        for i in range(1,7):
            a=live["agents"][str(i)]
            db=self._db_summary(i,a["run_id"])
            classification=self.classify(a,db)
            entries[str(i)]={"agent":i,"mounted":a["mounted"],"health":a["health"],
              "phase":a["phase"],"iteration":a["iteration"],"run_id":a["run_id"],
              "active":a["active"],"classification":classification,
              "db_outcome":db["outcome"],
              "intervention":INCIDENT_TYPES.get(classification)}
        last=read_json(self.last_path)
        changes=[]
        for i in range(1,7):
            old=(last.get("agents") or {}).get(str(i)) or {}
            new=entries[str(i)]
            keys=("run_id","classification","db_outcome","phase","active")
            diff={k:{"was":old.get(k),"now":new.get(k)} for k in keys
                if old and old.get(k)!=new.get(k)}
            # Iterations are progress, not incidents; report only when completed,
            # the controller stopped, or the category changed.
            if diff or not old:
                changes.append({"agent":i,"change":diff or {"initial":new["classification"]}})
        snapshot={"ts":time.time(),"version":live["version"],"agents":entries,
                  "performance":live["perf"],"material_changes":changes}
        write_json(self.last_path,snapshot)
        if changes:
            with self.events_path.open("a",encoding="utf8") as f:
                for row in changes:
                    item={"ts":snapshot["ts"],**row}
                    f.write(json.dumps(item,ensure_ascii=False)+"\n")
        return snapshot

def _single_instance_lock(path):
    """Hold an OS-level lock during daemon lifetime (no duplicate watcher)."""
    path.parent.mkdir(parents=True,exist_ok=True)
    lock=path.open("a+b")
    try:
        lock.seek(0,2)
        if lock.tell()==0:
            lock.write(b"0");lock.flush()
        lock.seek(0)
        if os.name=="nt":
            import msvcrt
            msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        return lock
    except (OSError,IOError) as exc:
        lock.close()
        raise RuntimeError("SUPERVISOR_ALREADY_RUNNING") from exc

def main():
    cli=argparse.ArgumentParser()
    cli.add_argument("--once",action="store_true")
    cli.add_argument("--daemon",action="store_true")
    cli.add_argument("--interval",type=int,default=60)
    ns=cli.parse_args()
    if ns.interval<30:cli.error("interval >= 30 seconds")
    sup=Supervisor()
    if not ns.daemon:
        print(json.dumps(sup.poll(),ensure_ascii=False))
        return
    lock=_single_instance_lock(sup.plane.state/"supervisor.lock")
    print(json.dumps({"status":"SUPERVISOR_STARTED","interval":ns.interval}),
          flush=True)
    while True:
        try:
            snap=sup.poll()
            if snap["material_changes"]:
                print(json.dumps({"changes":snap["material_changes"]},
                                  ensure_ascii=False),flush=True)
        except Exception as exc:
            # Do not print credentials/URLs or raw external body.
            print(json.dumps({"status":"MONITOR_ERROR",
                              "type":type(exc).__name__}),flush=True)
        time.sleep(ns.interval)

if __name__=="__main__":
    main()
