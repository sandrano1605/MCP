"""Launch detached six-agent watcher without touching the ChatGPT UI."""
import json
import os
import subprocess
import sys
from pathlib import Path
from control_plane import Plane

root=Path(__file__).resolve().parent
status=Plane().status()
if not status.get("version"):
    raise SystemExit("NO_GO_APP_UNAVAILABLE")
local=Path(os.environ.get("LOCALAPPDATA") or Path.home()/"AppData"/"Local")
log=local/"central_agentica_control"/"supervisor_stdout.log"
log.parent.mkdir(parents=True,exist_ok=True)
kwargs={}
if os.name=="nt":
    kwargs["creationflags"]=subprocess.DETACHED_PROCESS|subprocess.CREATE_NEW_PROCESS_GROUP
with log.open("ab") as out:
    proc=subprocess.Popen([sys.executable,"-X","utf8",str(root/"supervisor.py"),
             "--daemon","--interval","60"],cwd=root,stdin=subprocess.DEVNULL,
            stdout=out,stderr=subprocess.STDOUT,close_fds=True,**kwargs)
print(json.dumps({"status":"START_REQUESTED","pid":proc.pid,
                  "log_local_only":str(log),"app_version":status["version"]}))
