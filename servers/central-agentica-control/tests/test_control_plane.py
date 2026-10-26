import json
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from control_plane import Plane,Api,Refused,digest,chat_url,read_json
from supervisor import Supervisor

URL="https://chatgpt.com/g/g-p-test/c/1234-abcdef"
RUN="a"*32

class FakeApi:
    def __init__(self):
        self.calls=[]
        self.panels=[1,2,3,4]
        self.follow={str(i):{"is_active":False,"phase":"IDLE","current_iteration":0,
            "max_iterations":100,"run_id":None} for i in range(1,7)}
        self.health={str(i):{"label":"LISTO","generating":False,
            "transport_queue_size":0,"transport_pending":False,
            "transport_failed":"","last_dom_sample_age_seconds":1} for i in range(1,7)}
        self.dom={"url":URL,"ready":True,"finalized":True,"isGenerating":False,
          "draft":"","blocked":False,"interrupted":False,"deliveryTimeout":False,
          "responseLoadFailed":False,"rateLimit":False,"contextLimit":False,
          "lastAssistantAfterLastUser":True,"turn":"4",
          "userText":"Continue "+RUN,"text":""}
    def call(self,path,body=None):
        self.calls.append((path,body))
        if path=="/api/status":return {"version":"5.7.5","panels":self.panels}
        if path=="/api/autosigue/status":return self.follow
        if path=="/api/agent-health":return {"agents":self.health}
        if path=="/api/performance":return {"cpu_percent":15,"pressure":"NORMAL"}
        if path=="/api/eval":return {"result":json.dumps(self.dom)}
        if path=="/api/layout":
            self.panels=list(range(1,body["count"]+1))
            return {"status":"SUCCESS"}
        if path=="/api/autosigue/resume":return {"status":"ACCEPTED"}
        if path=="/api/autosigue/start":return {"status":"SUCCESS"}
        raise AssertionError(path)

class PlaneTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.app=self.root/"app";self.app.mkdir()
        (self.app/"runtime_v3.py").write_text('STATE_JS = "document.body.textContent"',encoding="utf8")
        self.dbroot=self.root/"data";self.dbroot.mkdir()
        db=sqlite3.connect(self.dbroot/"task_memory_v3.sqlite3")
        db.execute("CREATE TABLE runs(id TEXT PRIMARY KEY, goal TEXT, mode TEXT, state TEXT, created REAL)")
        db.execute("CREATE TABLE turns(id INTEGER PRIMARY KEY, run TEXT, agent INTEGER, url TEXT, turn TEXT, text TEXT, checkpoint TEXT, created REAL)")
        db.execute("INSERT INTO runs VALUES(?,?,?,?,?)",
            (RUN,"Inspect isolated LOCAL data only","followup","RUNNING",time.time()))
        self.cp={"run_id":RUN,"status":"working","summary":"Tests pending",
                 "completed":["Initial read"],"pending":["Test locally"],"evidence":["PASS"],
                 "safe_next_steps":["Read and verify"]}
        self.fence=chr(96)*3
        final="Result\n"+self.fence+"task-state\n"+json.dumps(self.cp)+"\n"+self.fence
        db.execute("INSERT INTO turns(run,agent,url,turn,text,checkpoint,created) VALUES(?,?,?,?,?,?,?)",
            (RUN,4,URL,"3",final,json.dumps(self.cp),time.time()))
        db.commit();db.close()
        self.api=FakeApi()
        self.api.dom["text"]=final
        self.plane=Plane(api=self.api,state=self.root/"state",app=self.app,task=self.dbroot)
    def tearDown(self):self.tmp.cleanup()
    def test_status_six_including_missing(self):
        s=self.plane.status()
        self.assertEqual(len(s["agents"]),6)
        self.assertFalse(s["agents"]["6"]["mounted"])
        self.assertFalse(s["all_six_mounted"])
    def test_loopback_only(self):
        for addr in ("http://192.168.1.1:8792","https://127.0.0.1:8792",
                     "http://example.com", "http://127.0.0.1:8792/x"):
            with self.assertRaises(Refused):Api(addr)
    def test_agent_dom_no_prompt_leak(self):
        a=self.plane.agent(4,detail=True)
        self.assertTrue(a["dom"]["finalized"])
        self.assertNotIn("userText",str(a))
        self.assertNotIn("Result",str(a))
    def test_layout_prepared_no_implicit_write(self):
        p=self.plane.prepare_layout(6)
        self.assertEqual(len(self.api.panels),4)
        self.assertEqual(p["status"],"PREPARED")
        with self.assertRaises(Refused):
            self.plane.approve(p["approval_token"],"yes")
        result=self.plane.approve(p["approval_token"],"APROBAR_CAMBIO_CONTROLADO")
        self.assertEqual(result["status"],"ACCEPTED_AWAITING_STATUS_RECHECK")
        self.assertEqual(len(self.api.panels),6)
        with self.assertRaises(Refused):
            self.plane.approve(p["approval_token"],"APROBAR_CAMBIO_CONTROLADO")
    def test_layout_reduction_blocked(self):
        with self.assertRaises(Refused):self.plane.prepare_layout(2)
    def test_resume_with_no_persistent_snapshot_refused(self):
        with self.assertRaisesRegex(Refused,"NO_MATCHING_RUN_SNAPSHOT"):
            self.plane.prepare_resume(4)
    def test_resume_verified(self):
        saved={"agents":{"4":{"run_id":RUN,"active":True,"expected_url":URL,
            "current_iteration":4,"max_iterations":100,"rollovers":0}}}
        from control_plane import write_json
        write_json(self.dbroot/"recovery_runs_v575.json",saved)
        p=self.plane.prepare_resume(4)
        self.assertEqual(p["status"],"PREPARED")
        resp=self.plane.approve(p["approval_token"],"APROBAR_CAMBIO_CONTROLADO")
        self.assertEqual(resp["action"],"resume")
        post=[(r,b) for r,b in self.api.calls if r=="/api/autosigue/resume"]
        self.assertEqual(len(post),1)
        self.assertEqual(post[0][1]["run_id"],RUN)
        self.assertTrue(post[0][1]["solo_enabled"])
    def test_resume_draft_blocked(self):
        self.api.dom["draft"]="vamos"
        with self.assertRaisesRegex(Refused,"EDITOR_DRAFT_OR_RESPONSE_NOT_SAFE"):
            self.plane.prepare_resume(4)
    def test_resume_unfinished_blocked(self):
        self.api.dom["finalized"]=False
        with self.assertRaisesRegex(Refused,"LATEST_ASSISTANT_NOT_FINAL"):
            self.plane.prepare_resume(4)
    def test_resume_active_blocked(self):
        self.api.follow["4"]["is_active"]=True
        with self.assertRaisesRegex(Refused,"ACTIVE_OR_UNCERTAIN_RUN"):
            self.plane.prepare_resume(4)
    def test_plan_state_changes_block(self):
        p=self.plane.prepare_layout(6)
        self.api.panels=list(range(1,7))
        with self.assertRaisesRegex(Refused,"STATE_CHANGED_REPLAN"):
            self.plane.approve(p["approval_token"],"APROBAR_CAMBIO_CONTROLADO")
    def test_start_does_not_duplicate_active_db_run(self):
        with self.assertRaisesRegex(Refused,"PREVIOUS_RUN_NEEDS_RECONCILIATION"):
            self.plane.prepare_start(4)
    def test_start_uncertain_previous_run_never_duplicated(self):
        db=sqlite3.connect(self.dbroot/"task_memory_v3.sqlite3")
        db.execute("UPDATE runs SET state=? WHERE id=?",
            ("RESPONSE_TIMEOUT_UNCONFIRMED",RUN))
        db.commit();db.close()
        with self.assertRaisesRegex(Refused,"PREVIOUS_RUN_NEEDS_RECONCILIATION"):
            self.plane.prepare_start(4)

    def test_safe_terminal_run_can_prepare_contextual_solo(self):
        db=sqlite3.connect(self.dbroot/"task_memory_v3.sqlite3")
        db.execute("UPDATE runs SET state=? WHERE id=?",("TIME_LIMIT",RUN))
        db.commit();db.close()
        p=self.plane.prepare_start(4,mode="solo")
        self.assertEqual(p["status"],"PREPARED")
        res=self.plane.approve(p["approval_token"],"APROBAR_CAMBIO_CONTROLADO")
        self.assertEqual(res["action"],"start")
        body=[b for path,b in self.api.calls if path=="/api/autosigue/start"][0]
        self.assertTrue(body["solo_enabled"])
        self.assertIn("safe",body["prompt_a"].lower())

    def test_context_no_full_chat_text(self):
        c=self.plane.context(4)
        self.assertEqual(c["runs"][0]["run_id"],RUN)
        self.assertNotIn("Result",str(c))
    def test_issue_local_and_no_secret(self):
        r=self.plane.record_issue(1,"TIMEOUT_UNCONFIRMED","Only safe metadata")
        self.assertEqual(r["status"],"RECORDED_LOCAL_ONLY")
        self.assertNotIn("chatgpt.com",self.plane.issues_file.read_text())
    def test_supervisor_completion_not_guessed(self):
        self.api.follow["4"].update(is_active=False,run_id=RUN,
            phase="DECLARED_DONE_WITH_EVIDENCE")
        sup=Supervisor(self.plane)
        first=sup.poll()
        self.assertNotEqual(first["agents"]["4"]["classification"],"DONE_CONFIRMED")
        db=sqlite3.connect(self.dbroot/"task_memory_v3.sqlite3")
        cp={**self.cp,"status":"done","pending":[]}
        db.execute("UPDATE turns SET checkpoint=? WHERE run=?",
            (json.dumps(cp),RUN))
        db.execute("UPDATE runs SET state=? WHERE id=?",
            ("DECLARED_DONE_WITH_EVIDENCE",RUN))
        db.commit();db.close()
        second=sup.poll()
        self.assertEqual(second["agents"]["4"]["classification"],"DONE_CONFIRMED")
    def test_snapshot_repeat_has_no_new_material_events(self):
        sup=Supervisor(self.plane)
        self.assertEqual(len(sup.poll()["material_changes"]),6)
        self.assertEqual(sup.poll()["material_changes"],[])
    def test_orchestrator_contextual_six_agent_plan(self):
        self.api.panels=list(range(1,7))
        db=sqlite3.connect(self.dbroot/"task_memory_v3.sqlite3")
        rid="b"*32
        db.execute("INSERT INTO runs VALUES(?,?,?,?,?)",
            (rid,"Legacy external task","followup","RESPONSE_TIMEOUT_UNCONFIRMED",time.time()))
        db.execute("INSERT INTO turns(run,agent,url,turn,text,checkpoint,created) VALUES(?,?,?,?,?,?,?)",
            (rid,6,URL,"3","Uncertain response",json.dumps(self.cp),time.time()))
        db.commit();db.close()
        plan=self.plane.orchestrator_plan()
        self.assertFalse(plan["state_changes"])
        self.assertEqual(len(plan["agents"]),6)
        action6=plan["agents"][5]["action"]
        self.assertEqual(action6,"RECONCILE_PREVIOUS_RUN")
        self.assertNotIn("/api/prompt",[route for route,_ in self.api.calls])

    def test_no_progress_has_explicit_incident_code(self):
        self.api.health["1"]["label"]="LENTO"
        self.api.follow["1"].update(is_active=True,phase="RESPONSE")
        output=Supervisor(self.plane).poll()
        self.assertEqual(output["agents"]["1"]["classification"],"NO_PROGRESS")
        incident=self.plane.issues_file.read_text(encoding="utf8")
        self.assertIn('"code": "NO_PROGRESS"',incident)

    def test_auto_incident_captured_once_on_change(self):
        self.api.health["4"]["label"]="LENTO"
        self.api.follow["4"].update(is_active=True,phase="RESPONSE")
        sup=Supervisor(self.plane)
        first=sup.poll()
        self.assertEqual(first["agents"]["4"]["classification"],"NO_PROGRESS")
        n=len(self.plane.issues_file.read_text(encoding="utf8").splitlines())
        self.assertGreaterEqual(n,1)
        sup.poll()
        self.assertEqual(len(self.plane.issues_file.read_text(encoding="utf8").splitlines()),n)

    def test_slow_health_with_live_generation_is_not_stall(self):
        # La etiqueta LENTO por sí sola no prueba una detención.
        self.api.health["4"]["label"]="LENTO"
        self.api.health["4"]["generating"]=True
        self.api.follow["4"].update(is_active=True,phase="RESPONSE")
        result=Supervisor(self.plane).poll()
        self.assertEqual(result["agents"]["4"]["classification"],"ACTIVE")
        issues=self.plane.issues_file
        self.assertFalse(issues.exists() and "NO_PROGRESS" in issues.read_text(encoding="utf8"))

    def test_chatgpt_error_not_falsely_active(self):
        self.api.health["3"]["label"]="ERROR"
        self.api.follow["3"].update(is_active=True,phase="RESPONSE",current_iteration=10)
        result=Supervisor(self.plane).poll()
        self.assertEqual(result["agents"]["3"]["classification"],"CHATGPT_ERROR")
        self.assertEqual(result["agents"]["3"]["intervention"],
                         "Inspect visible ChatGPT error; preserve draft and reconcile prior turn")
        issues=self.plane.issues_file.read_text(encoding="utf8")
        self.assertIn("RESPONSE_UNVERIFIED",issues)
        self.assertNotIn("/api/prompt",[route for route,_ in self.api.calls])

    def test_missing_telemetry_never_active(self):
        self.api.health["1"]["label"]="SIN DATOS"
        self.api.follow["1"]["is_active"]=True
        result=Supervisor(self.plane).poll()
        self.assertEqual(result["agents"]["1"]["classification"],"NO_TELEMETRY")

    def test_mcp_import(self):
        from server import build_server
        m=build_server(self.plane)
        self.assertIsNotNone(m)

if __name__=="__main__":unittest.main()
