"""Safe local CLI for access through APPANOL Trabajo, without plugin registration.

Examples:
 python cli.py status
 python cli.py monitor
 python cli.py agent 3
 python cli.py context 3
 python cli.py prepare-layout 6
 python cli.py prepare-restore 4
 python cli.py approve <token> APROBAR_CAMBIO_CONTROLADO
"""
from __future__ import annotations
import argparse
import json
import sys
from control_plane import Plane, Refused
from supervisor import Supervisor

def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("command",choices=("status","monitor","agent","context",
        "prepare-layout","prepare-start","prepare-restore","approve","record-incident","orchestrator-plan","recovery-diagnosis"))
    p.add_argument("arg1",nargs="?")
    p.add_argument("arg2",nargs="?")
    p.add_argument("arg3",nargs="?")
    opt=p.parse_args(argv)
    cp=Plane()
    try:
        args=(opt.arg1,opt.arg2,opt.arg3)
        if opt.command=="status":v=cp.status()
        elif opt.command=="monitor":v=Supervisor(cp).poll()
        elif opt.command=="recovery-diagnosis":v=cp.recovery_diagnosis(args[0])
        elif opt.command=="orchestrator-plan":v=cp.orchestrator_plan()
        elif opt.command=="agent":v=cp.agent(args[0],detail=True)
        elif opt.command=="context":v=cp.context(args[0])
        elif opt.command=="prepare-layout":v=cp.prepare_layout(int(args[0] or 6))
        elif opt.command=="prepare-start":
            v=cp.prepare_start(args[0],mode=args[1] or "solo",iterations=int(args[2] or 100))
        elif opt.command=="prepare-restore":
            v=cp.prepare_resume(args[0],mode=args[1] or "solo")
        elif opt.command=="approve":v=cp.approve(args[0],args[1])
        elif opt.command=="record-incident":v=cp.record_issue(args[0],args[1],args[2])
        print(json.dumps(v,ensure_ascii=False))
        return 0
    except (Refused,ValueError,TypeError) as exc:
        print(json.dumps({"status":"REFUSED","reason":str(exc)},ensure_ascii=False))
        return 3

if __name__=="__main__":
    sys.exit(main())
