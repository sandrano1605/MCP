"""Tested stdio MCP tool surface for Central Agentica AF9328.

Commands that change state require two stages: prepare -> explicit approval.
No generic shell tool, no arbitrary JavaScript, and no direct ChatGPT retries.
"""
import json
import os
from pathlib import Path
from control_plane import Plane, Refused
from supervisor import Supervisor

def build_server(plane=None):
    from mcp.server.fastmcp import FastMCP
    mcp=FastMCP("central-agentica-orchestrator")
    ctrl=plane or Plane()

    def safe(call):
        try:return call()
        except Refused as exc:
            return {"status":"REFUSED","reason":str(exc)}
        except Exception as exc:
            return {"status":"ERROR","error_class":type(exc).__name__}

    @mcp.tool()
    def central_system_status() -> dict:
        """Check all six agents, phases, run IDs and local hardware pressure."""
        return safe(ctrl.status)

    @mcp.tool()
    def central_agent_status(agent_id:int,with_browser:bool=False)->dict:
        """Inspect one agent; with_browser reads current DOM, never edits it."""
        return safe(lambda:ctrl.agent(agent_id,with_browser))

    @mcp.tool()
    def central_task_context(agent_id:int)->dict:
        """Fetch verified per-agent task goal, checkpoint, completed and pending."""
        return safe(lambda:ctrl.context(agent_id))

    @mcp.tool()
    def central_recovery_diagnosis(agent_id:int)->dict:
        """Read-only V5.7.6 SOLO/Sígueme safe-path diagnosis for one agent."""
        return safe(lambda:ctrl.recovery_diagnosis(agent_id))

    @mcp.tool()
    def central_orchestrator_plan()->dict:
        """Read-only contextual plan for all six agents; never resends."""
        return safe(ctrl.orchestrator_plan)

    @mcp.tool()
    def central_monitor_once()->dict:
        """Read six-agent progress, completion certification and incidents."""
        return safe(lambda:Supervisor(ctrl).poll())

    @mcp.tool()
    def central_prepare_six_agents()->dict:
        """Prepare 6-panel layout; existing agents preserved, no immediate write."""
        return safe(lambda:ctrl.prepare_layout(6))

    @mcp.tool()
    def central_prepare_start(agent_id:int,mode:str="solo",iterations:int=100)->dict:
        """Plan a contextual new run; rejects uncertain or active prior runs."""
        return safe(lambda:ctrl.prepare_start(agent_id,mode,iterations))

    @mcp.tool()
    def central_prepare_restore(agent_id:int,mode:str="solo")->dict:
        """Plan same run_id restoration only when a final owned checkpoint is verified."""
        return safe(lambda:ctrl.prepare_resume(agent_id,mode))

    @mcp.tool()
    def central_approve_action(approval_token:str,confirmation:str)->dict:
        """Execute exactly one prepared state change; confirmation must equal APROBAR_CAMBIO_CONTROLADO.

        No automatic retry after a timeout; confirm resulting state separately.
        """
        return safe(lambda:ctrl.approve(approval_token,confirmation))

    @mcp.tool()
    def central_record_incident(agent_id:int,code:str,evidence:str)->dict:
        """Record incident metadata locally for continuous-improvement regression."""
        return safe(lambda:ctrl.record_issue(agent_id,code,evidence))

    @mcp.tool()
    def central_continuous_improvement()->dict:
        """Summarize recurring incidents and regression tests to add."""
        from improvement import report
        return safe(lambda:report(ctrl))

    @mcp.tool()
    def central_read_incidents(limit:int=20)->dict:
        """Review recent local incident categories without exposing full prompts."""
        limit=max(1,min(int(limit),50))
        p=ctrl.issues_file
        if not p.exists():return {"incidents":[]}
        rows=[]
        for line in p.read_text(encoding="utf8").splitlines()[-limit:]:
            try:rows.append(json.loads(line))
            except ValueError:pass
        return {"incidents":rows}

    return mcp

def main():
    mcp=build_server()
    mcp.run(transport="stdio")

if __name__=="__main__":
    main()
