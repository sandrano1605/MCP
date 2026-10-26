"""Regression gates for the documented V5.7.6 happy/safe paths.

No test can write ChatGPT, PRD, or the real SQLite DB.
"""
import json
import unittest
from recovery_protocol_v576 import decide,verified_checkpoint

RUN="a"*32
URL="https://chatgpt.com/g/g-p-11111111111111111111111111111111-proyecto/c/1"
BASE={"mounted":True,"active":False,"phase":"IDLE","run_id":RUN,
      "transport_failed":"","generating":False,"queue":0,"transport_pending":False}
DOM={"url":URL,"ready":True,"isGenerating":False,"finalized":True,
     "draft":"","blocked":False,"alerts":"","lastAssistantAfterLastUser":True,
     "userText":"Continue same run "+RUN}
CP={"run_id":RUN,"status":"working","summary":"Objective persists",
    "completed":["A"],"pending":["B"],"evidence":[{"test":"PASS"}],
    "safe_next_steps":["B"]}
SAVED={"run_id":RUN,"active":True,"expected_url":URL}

def verdict(a=None,d=None,cp=None,db="RUNNING",saved=None,project=True):
    return decide(agent_id=4,controller=a if a is not None else BASE,
        dom=d if d is not None else DOM,db_state=db,
        checkpoint=cp if cp is not None else CP,
        saved=saved if saved is not None else SAVED,project_matches=project)

class RecoveryProtocolTests(unittest.TestCase):
    def test_valid_same_run_checkpoint_prepare_restore(self):
        x=verdict()
        self.assertEqual(x["action"],"PREPARE_SAME_RUN_RESTORE")
        self.assertTrue(x["can_prepare_restore"])
        self.assertFalse(x["safe_to_resend"])

    def test_same_run_expected_url_mismatch_blocks_restore(self):
        x=verdict(saved={**SAVED,"expected_url":URL+"/wrong"})
        self.assertEqual(x["action"],"RECONCILE_PREVIOUS_RUN")

    def test_same_run_id_mismatch_blocks_restore(self):
        x=verdict(saved={**SAVED,"run_id":"b"*32})
        self.assertEqual(x["action"],"RECONCILE_PREVIOUS_RUN")

    def test_previous_final_checkpoint_missing_evidence_blocks(self):
        x=verdict(cp={**CP,"evidence":[]})
        self.assertFalse(x["can_prepare_restore"])

    def test_last_reply_not_owned_blocks_restore(self):
        x=verdict(d={**DOM,"lastAssistantAfterLastUser":False})
        self.assertFalse(x["can_prepare_restore"])

    def test_a3_unsent_draft_on_reloaded_chat_blocks_even_if_final(self):
        # Real-life failure: a previous answer may be final while a long
        # duplicate instruction remains in the editor after controlled reload.
        x=verdict(a={**BASE,"active":True,"phase":"WAITING_SAFE_WORK",
           "transport_failed":"RESPONSE_TIMEOUT_UNCONFIRMED"},
            d={**DOM,"draft":"AGENTE 3 CONTINUA..."})
        self.assertEqual(x["action"],"PRESERVE_DRAFT")
        self.assertFalse(x["safe_to_resend"])

    def test_a3_uncertain_delivery_without_draft_still_blocks(self):
        x=verdict(a={**BASE,"active":True,"phase":"WAITING_SAFE_WORK",
           "transport_failed":"RESPONSE_TIMEOUT_UNCONFIRMED"})
        self.assertEqual(x["action"],"RECONCILE_UNCERTAIN")

    def test_repeated_click_after_unknown_error_is_not_authorized(self):
        x=verdict(d={**DOM,"blocked":True,"alerts":"Unknown error Retry"})
        self.assertEqual(x["action"],"RECONCILE_ERROR")
        self.assertFalse(x["safe_to_resend"])

    def test_streaming_response_only_watch(self):
        x=verdict(a={**BASE,"active":True,"generating":True})
        self.assertEqual(x["action"],"OBSERVE_STREAM")

    def test_controller_active_on_good_phase_not_restartable(self):
        x=verdict(a={**BASE,"active":True,"phase":"RESPONSE"})
        self.assertEqual(x["action"],"KEEP_RUNNING")
        self.assertFalse(x["can_prepare_restore"])
        self.assertFalse(x["can_prepare_start"])

    def test_rollover_same_project_requires_editor_verification(self):
        x=verdict(a={**BASE,"active":True,"phase":"ROLLOVER_WAIT_EDITOR"})
        self.assertEqual(x["action"],"VERIFY_ROLLOVER")

    def test_a5_contextual_new_start_requires_terminal_previous_run(self):
        x=verdict(db="MANUAL_STOP")
        self.assertEqual(x["action"],"PREPARE_CONTEXTUAL_START")
        self.assertTrue(x["can_prepare_start"])
        self.assertFalse(x["safe_to_resend"])

    def test_a5_nonterminal_run_never_starts_new(self):
        x=verdict(db="RESPONSE_TIMEOUT_UNCONFIRMED")
        self.assertFalse(x["can_prepare_start"])

    def test_wrong_project_blocks_any_transition(self):
        x=verdict(project=False)
        self.assertEqual(x["action"],"PROJECT_MISMATCH")

    def test_terminal_done_requires_explicit_verification(self):
        x=verdict(cp={**CP,"status":"done","pending":[]})
        self.assertEqual(x["action"],"VERIFY_DONE")
        self.assertFalse(x["can_prepare_start"])
        self.assertFalse(x["can_prepare_restore"])

    def test_queued_transport_refuses_any_second_send(self):
        x=verdict(a={**BASE,"queue":1})
        self.assertEqual(x["action"],"RECONCILE_DELIVERY")

    def test_unknown_missing_dom_blocks(self):
        x=decide(agent_id=4,controller=BASE,dom=None)
        self.assertEqual(x["action"],"RESTORE_READABILITY")

    def test_verified_checkpoint_fence_and_correct_run(self):
        fence=chr(96)*3
        t="text\n"+fence+"task-state\n"+json.dumps(CP)+"\n"+fence
        self.assertEqual(verified_checkpoint(t,RUN),CP)
        self.assertIsNone(verified_checkpoint(t,"b"*32))

    def test_checkpoint_prose_not_sufficient(self):
        self.assertIsNone(verified_checkpoint("Done. All tests passed.",RUN))

    def test_missing_evidence_data_fails_checkpoint(self):
        fence=chr(96)*3
        t=fence+"task-state\n"+json.dumps({**CP,"evidence":"PASS"})+"\n"+fence
        self.assertIsNone(verified_checkpoint(t,RUN))

    def test_all_verdicts_refuse_automatic_resend(self):
        variants=[
            verdict(),verdict(a={**BASE,"active":True,"phase":"RESPONSE"}),
            verdict(db="MANUAL_STOP"),
            verdict(a={**BASE,"transport_failed":"RESPONSE_TIMEOUT_UNCONFIRMED"}),
            verdict(d={**DOM,"draft":"original user work"}),
        ]
        self.assertTrue(all(v["safe_to_resend"] is False for v in variants))

if __name__=="__main__":unittest.main()
