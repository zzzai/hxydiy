"""Exercise orchestration safety without contacting production."""
import contextlib
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import controlled_batch as cb
from session import validate_request, request
from contracts import Stop
import uuid


class RequestTests(unittest.TestCase):
    def test_only_exact_fixed_action_and_package(self):
        value={"id":str(uuid.uuid4()),"action":"controlled_sync","package_sha256":"a"*64}
        self.assertEqual(validate_request(value,"a"*64),value["id"])
        for change in [{"action":"apply"},{"package_sha256":"b"*64},{"command":"anything"}]:
            with self.assertRaises(Stop):validate_request(dict(value,**change),"a"*64)

    def test_pending_request_not_replaced(self):
        with tempfile.TemporaryDirectory() as d:
            a=request(Path(d),"a"*64); b=request(Path(d),"a"*64)
            self.assertEqual(a["request_id"],b["request_id"])


class ApplyTests(unittest.TestCase):
    def fixture(self, root):
        batch=cb.Batch.__new__(cb.Batch);batch.root=root;batch.container="/tmp/synthetic"
        batch.request={"source_keyset_sha256":"a"*64,"verification_date":"2026-11-15"}
        manifest={"cards":2,"new_users":1,"files":{"input":{"sha256":"b"*64}}}
        cb.save(root,"candidate-manifest.json",manifest)
        cb.save(root,"execution-config.json",{"manifest_sha256":cb.sha(root/"candidate-manifest.json")})
        cb.save(root,"backup-recovery-result.json",{"status":"backup_and_real_recovery_passed","apply_executed":False})
        cb.save(root,"continuity-result.json",{"status":"passed","unexpected_account_changes":0})
        cb.save(root,"formal-preflight.json",{})
        cb.save(root,"recovery-evidence.json",{})
        batch.release_locks=lambda:contextlib.nullcontext()
        batch.identity=lambda _:None;batch.persist=lambda _:None
        return batch

    def test_failed_recovery_never_calls_apply(self):
        with tempfile.TemporaryDirectory() as d:
            batch=self.fixture(Path(d))
            (batch.root/"backup-recovery-result.json").write_text('{"status":"failed","apply_executed":false}')
            batch.run=lambda *args:self.fail("no subprocess allowed")
            with self.assertRaises(AssertionError):batch.apply_once()
            self.assertFalse((batch.root/"formal-apply-attempt.json").exists())

    def test_prior_change_never_calls_apply(self):
        with tempfile.TemporaryDirectory() as d:
            batch=self.fixture(Path(d))
            (batch.root/"continuity-result.json").write_text('{"status":"passed","unexpected_account_changes":1}')
            batch.run=lambda *args:self.fail("no subprocess allowed")
            with self.assertRaises(AssertionError):batch.apply_once()

    def test_unknown_attempt_cannot_retry(self):
        with tempfile.TemporaryDirectory() as d:
            batch=self.fixture(Path(d));cb.save(batch.root,"formal-apply-attempt.json",{"unknown":True})
            calls=[]
            def run(label,args):
                calls.append(label)
                return json.dumps({"status":"passed","users":10,"cards":3}).encode()
            batch.run=run
            with self.assertRaises(FileExistsError):batch.apply_once()
            self.assertEqual(calls,["immediate-before-apply"])
            self.assertFalse((batch.root/"PRODUCTION-RESULT.json").exists())

    def test_one_apply_protection_and_zero_replay_required(self):
        with tempfile.TemporaryDirectory() as d:
            batch=self.fixture(Path(d));calls=[]
            def run(label,args):
                calls.append((label,args))
                if label=="formal-apply":
                    self.assertIn("--approved-manifest-sha256",args)
                    self.assertIn("--preflight-sha256",args)
                    self.assertIn("--recovery-sha256",args)
                    return json.dumps({"applied":True,"new_cards":2,"new_users":1,"protected_old_records_unchanged":True}).encode()
                if label=="replay-preview":
                    self.assertNotIn("--apply",args)
                    return b'{"mode":"already-applied","applied":false,"new_cards":0,"new_users":0}'
                return json.dumps({"status":"passed","users":11 if label=="immediate-after-apply" else 10,
                    "cards":5 if label=="immediate-after-apply" else 3,"old_users_and_cards_unchanged":True,
                    "financial_tables_unchanged":True}).encode()
            batch.run=run
            result=batch.apply_once()
            self.assertEqual(result["new_cards"],2)
            self.assertEqual(sum(label=="formal-apply" for label,args in calls),1)
            self.assertTrue(result["old_users_cards_wallets_unchanged"])
            with self.assertRaises(FileExistsError):batch.apply_once()
            self.assertEqual(sum(label=="formal-apply" for label,args in calls),1)


class BridgeTests(unittest.TestCase):
    def test_no_new_never_contacts_import_server(self):
        import bridge
        with tempfile.TemporaryDirectory() as d:
            with patch.object(bridge.runner,"run",return_value={"status":"no_new","new_cards":0}), patch.object(bridge,"apply") as apply:
                self.assertEqual(bridge.sync_once(Path(d),lambda _:None)["status"],"no_new")
                apply.assert_not_called()

    def test_unknown_server_outcome_latches_without_retry(self):
        import bridge
        import runner
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);run_id="20261115T000000Z-aaaaaaaa"
            (root/"runs"/run_id).mkdir(parents=True)
            report={"status":"readonly_passed","new_cards":1,"run_id":run_id}
            with patch.object(bridge.runner,"run",return_value=report), patch.object(bridge,"apply",side_effect=TimeoutError("private data")), patch.object(bridge.runner,"notify",return_value="test_only") as notify:
                result=bridge.sync_once(root,lambda _:None)
                self.assertEqual(result["status"],"blocked")
                notify.assert_called_once()
            self.assertEqual(runner.run(root,lambda _:self.fail("no collection"),probe_fn=lambda:self.fail("no probe"))["status"],"blocked_latched")
            self.assertNotIn("private data",(root/"report.json").read_text())


if __name__ == "__main__":unittest.main()
