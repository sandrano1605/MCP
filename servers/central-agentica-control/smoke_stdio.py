"""Real MCP stdio smoke test against the already-running local Central Agéntica.

No state changes: handshake, tool discovery, read-only system and one-agent check.
"""
import asyncio
import json
import os
import sys
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    here=Path(__file__).resolve().parent
    par=StdioServerParameters(command=sys.executable,args=[str(here/"server.py")],
                              env=dict(os.environ))
    async with stdio_client(par) as (read,write):
        async with ClientSession(read,write) as session:
            await session.initialize()
            tools=await session.list_tools()
            names=sorted(t.name for t in tools.tools)
            assert "central_monitor_once" in names
            assert "central_prepare_restore" in names
            status=await session.call_tool("central_system_status",arguments={})
            if status.isError:raise RuntimeError("MCP_SYSTEM_TOOL_FAILED")
            payload=status.structuredContent
            if not payload:
                item=status.content[0]
                payload=json.loads(getattr(item,"text","{}"))
            value=payload.get("result",payload)
            assert value.get("version","").startswith("5.7.5")
            assert len(value.get("agents",{}))==6
            one=await session.call_tool("central_agent_status",arguments={"agent_id":1,"with_browser":False})
            assert not one.isError
            plan=await session.call_tool("central_orchestrator_plan",arguments={})
            assert not plan.isError
            pcontent=plan.structuredContent
            if not pcontent:
                pcontent=json.loads(getattr(plan.content[0],"text","{}"))
            pvalue=pcontent.get("result",pcontent)
            assert len(pvalue.get("agents",[]))==6
            diag=await session.call_tool("central_recovery_diagnosis",arguments={"agent_id":3})
            assert not diag.isError
            dcontent=diag.structuredContent
            if not dcontent:
                dcontent=json.loads(getattr(diag.content[0],"text","{}"))
            dvalue=dcontent.get("result",dcontent)
            assert dvalue.get("agent")==3
            assert dvalue.get("mutations")==0
            assert dvalue.get("decision",{}).get("safe_to_resend") is False
            print(json.dumps({"mcp_protocol":"PASS","tools":len(names),
                    "tool_names":names,"version":value["version"],
                    "panels":value.get("panels"),"read_only_checks":4},
                    ensure_ascii=False))

if __name__=="__main__":asyncio.run(main())
