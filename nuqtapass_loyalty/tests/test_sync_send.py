import json
from datetime import datetime, timedelta
from unittest.mock import patch

from odoo import SUPERUSER_ID, api, fields, sql_db
from odoo.tests import TransactionCase, tagged

from odoo.addons.nuqtapass_loyalty.lib.client import ApiResult, NuqtaPassClient


def ok(data):
    return ApiResult(True, 201, data, None, None, False)


def fail(retryable, status=503, error="Service unavailable"):
    return ApiResult(False, status, None, error, None, retryable)


@tagged("post_install", "-at_install", "nuqtapass")
class TestSyncSend(TransactionCase):
    def setUp(self):
        super().setUp()
        self.Sync = self.env["nuqtapass.sync"].sudo()
        self.env["ir.config_parameter"].sudo().set_str("nuqtapass_loyalty.api_key", "sip_test")
        self.rec = self.Sync._queue({
            "kind": "sale", "channel": "till", "order_ref": "Shop/0001", "phone": "+96891234567",
            "amount": 2.5, "occurred_at": datetime(2026, 11, 9, 10, 0),
        })
        self.now = fields.Datetime.now() + timedelta(seconds=5)

    def _send(self, result, method="sale"):
        with patch.object(NuqtaPassClient, method, return_value=result) as mocked:
            self.Sync._send_due(now=self.now)
        return mocked

    def test_success_marks_done_and_keeps_only_result(self):
        # A Part 1 PosAnswer for a new customer's first stamp.
        mocked = self._send(ok({
            "transactionId": "t1", "kind": "SALE", "orderRef": "Shop/0001", "refundRef": None, "status": "OK",
            "cardId": "cccccccc-1111-4111-8111-111111111111", "duplicate": False,
            "result": {"cardType": "STAMPS", "stamps": 1, "newCustomer": True, "stampMinMilli": 0},
            "welcome": {"cardUrl": "https://nuqtapass.com/join/qahwa", "sms": "sms:+96891234567?body=Hi",
                        "whatsapp": "https://api.whatsapp.com/send?phone=96891234567&text=Hi", "message": "Hi"},
        }))
        mocked.assert_called_once_with(self.rec._payload())
        self.assertEqual(self.rec.state, "done")
        self.assertEqual(self.rec.attempts, 1)
        stored = json.loads(self.rec.response_json)
        self.assertEqual(stored, {"status": "OK", "duplicate": False, "result": {"cardType": "STAMPS", "stamps": 1}})
        self.assertEqual(self.rec.summary, "Stamps given: 1")

    def test_points_and_nothing(self):
        self._send(ok({"status": "OK", "duplicate": True, "result": {"cardType": "POINTS", "points": 12}}))
        self.assertEqual(self.rec.summary, "Points given: 12 · (NuqtaPass already had it)")
        self.rec.write({"response_json": json.dumps(
            {"status": "NOTHING", "duplicate": False, "result": {"cardType": "STAMPS", "reason": "BELOW_MINIMUM"}})})
        self.assertEqual(self.rec.summary, "Sent, nothing to give for this card")

    def test_pending_answer_is_retried(self):
        self._send(ok({"status": "PENDING", "duplicate": True, "result": None}))
        self.assertEqual(self.rec.state, "pending")
        self.assertEqual(self.rec.next_attempt_at, self.now + timedelta(minutes=1))
        self.assertEqual(self.rec.last_error, "NuqtaPass is still working on this order")

    def test_temporary_failure_waits_one_minute(self):
        self._send(fail(True))
        self.assertEqual(self.rec.state, "pending")
        self.assertEqual(self.rec.attempts, 1)
        self.assertEqual(self.rec.next_attempt_at, self.now + timedelta(minutes=1))
        self.assertEqual(self.rec.last_error, "Service unavailable")

    def test_not_due_is_not_sent(self):
        self._send(fail(True))
        mocked = self._send(ok({}))  # still `now`, next try is now + 1 min
        mocked.assert_not_called()

    def test_final_failure_goes_failed_at_once(self):
        self._send(fail(False, 400, "phone invalid"))
        self.assertEqual(self.rec.state, "failed")
        self.assertFalse(self.rec.next_attempt_at)

    def test_gives_up_after_last_try(self):
        self.rec.write({"attempts": 16})
        self._send(fail(True))
        self.assertEqual(self.rec.state, "failed")
        self.assertEqual(self.rec.attempts, 17)

    def test_no_key_is_temporary(self):
        self.env["ir.config_parameter"].sudo().set_str("nuqtapass_loyalty.api_key", False)
        self.Sync._send_due(now=self.now)
        self.assertEqual(self.rec.state, "pending")
        self.assertTrue(self.rec.last_error)

    def test_resend_resets_a_failed_row(self):
        self._send(fail(False, 400))
        self.rec.action_resend()
        self.assertEqual(self.rec.state, "pending")
        self.assertEqual(self.rec.attempts, 0)
        self.assertFalse(self.rec.last_error)

    def test_refund_calls_refund(self):
        refund = self.Sync._queue({
            "kind": "refund", "channel": "till", "order_ref": "Shop/0001", "refund_ref": "R1",
            "amount": 2.5, "occurred_at": datetime(2026, 11, 9, 11, 0),
        })
        self.rec.write({"state": "done"})
        # Part 1: the stamp was already used for a reward, so nothing comes back and the shortfall says so.
        self._send(ok({"kind": "REFUND", "status": "OK", "duplicate": False, "result": {
            "cardType": "STAMPS", "stamps": 0, "plannedStamps": 1, "shortfall": {"stamps": 1}, "reason": "ALREADY_USED"}}),
            method="refund")
        self.assertEqual(refund.state, "done")
        self.assertEqual(refund.summary, "Stamps already used, not taken back: 1")
        refund.write({"response_json": json.dumps(
            {"status": "OK", "duplicate": False, "result": {"cardType": "POINTS", "points": 4, "shortfall": {"points": 8}}})})
        self.assertEqual(refund.summary, "Points taken back: 4 · Points already used, not taken back: 8")

    def test_refund_always_sends_order_amount_and_return_uses(self):
        refund = self.Sync._queue({
            "kind": "refund", "channel": "till", "order_ref": "Shop/0001", "refund_ref": "R2", "amount": 0,
            "order_amount": 7.5, "return_uses": json.dumps({"points": 167, "credit": 2.5}),
            "occurred_at": datetime(2026, 11, 9, 11, 0),
        })
        body = refund._payload()
        self.assertEqual((body["amount"], body["orderAmount"], body["returnUses"]),
                         (0, 7.5, {"points": 167, "credit": 2.5}))
        plain = self.Sync._queue({
            "kind": "refund", "channel": "till", "order_ref": "Shop/0001", "refund_ref": "R3", "amount": 2.5,
            "order_amount": 2.5, "occurred_at": datetime(2026, 11, 9, 11, 0),
        })
        self.assertEqual(plain._payload()["returnUses"], {})
        # A row queued before this version has no order amount: never send 0 (NuqtaPass refuses it).
        old = self.Sync._queue({
            "kind": "refund", "channel": "till", "order_ref": "Shop/0001", "refund_ref": "R4", "amount": 2.5,
            "occurred_at": datetime(2026, 11, 9, 11, 0),
        })
        self.assertNotIn("orderAmount", old._payload())
        self.assertEqual(old._payload()["returnUses"], {})

    def test_refund_keeps_and_shows_what_came_back(self):
        refund = self.Sync._queue({
            "kind": "refund", "channel": "till", "order_ref": "Shop/0001", "refund_ref": "R5", "amount": 0,
            "order_amount": 7.5, "return_uses": json.dumps({"points": 167}),
            "occurred_at": datetime(2026, 11, 9, 11, 0),
        })
        self.rec.write({"state": "done"})
        self._send(ok({"kind": "REFUND", "status": "OK", "duplicate": False, "cardId": "x",
                       "result": {"cardType": "POINTS", "points": 0, "returned": {"r1": 167}},
                       "pointsReturned": 167, "creditReturned": 2.5, "usesReturned": 1, "rewardReturned": True,
                       "vouchersReturned": 1, "rewardNotReturned": False}), method="refund")
        stored = json.loads(refund.response_json)["result"]
        self.assertEqual({k: stored[k] for k in ("pointsReturned", "creditReturned", "usesReturned", "rewardReturned",
                                                  "vouchersReturned", "rewardNotReturned")},
                         {"pointsReturned": 167, "creditReturned": 2.5, "usesReturned": 1, "rewardReturned": True,
                          "vouchersReturned": 1, "rewardNotReturned": False})
        self.assertNotIn("returned", stored)
        self.assertEqual(refund.summary, "Points given back: 167 · Credit given back: 2.5 · Pack uses given back: 1 · "
                                         "Reward given back · Vouchers given back: 1")
        refund.write({"response_json": json.dumps({"status": "OK", "duplicate": False,
                                                   "result": {"rewardNotReturned": True}})})
        self.assertEqual(refund.summary, "The stamp card is no longer active: the reward was not given back")

    def test_summary_for_failed(self):
        self._send(fail(False, 400, "phone invalid"))
        self.assertIn("phone invalid", self.rec.summary)

    def test_wrong_phone_is_never_sent(self):
        # A row queued before phones were checked (the live "+9689417872"): refused here, no HTTP call.
        self.rec.write({"phone": "+9689417872"})
        mocked = self._send(ok({"status": "OK"}))
        mocked.assert_not_called()
        self.assertEqual(self.rec.state, "failed")
        self.assertTrue(self.rec.phone_invalid)
        self.assertEqual(self.rec.summary, "Phone number looks wrong: +9689417872")

    def test_resend_rechecks_the_phone(self):
        self.env.company.country_id = self.env.ref("base.om")
        self.rec.write({"phone": "+9689417872"})
        self._send(ok({"status": "OK"}))
        self.rec.action_resend()
        self.assertEqual(self.rec.state, "failed")  # still wrong: not queued again
        self.assertFalse(self.rec.next_attempt_at)
        with patch.object(type(self.Sync), "_nuqtapass_current_phone", return_value="9417 6872"):
            self.rec.action_resend()
        self.assertEqual((self.rec.state, self.rec.phone, self.rec.phone_invalid), ("pending", "+96894176872", False))

    def test_claim_takes_only_pending_rows(self):
        self.assertEqual(self.rec._claim(), self.rec)
        self.rec.write({"state": "done"})
        self.assertFalse(self.rec._claim())

    def test_row_claimed_elsewhere_is_skipped(self):
        with patch.object(type(self.Sync), "_claim", return_value=self.Sync.browse()):
            mocked = self._send(ok({"status": "OK"}))
        mocked.assert_not_called()
        self.assertEqual((self.rec.state, self.rec.attempts), ("pending", 0))


@tagged("post_install", "-at_install", "nuqtapass")
class TestSyncRowLock(TransactionCase):
    """A row another transaction is sending (locked) is skipped, with real separate database connections."""

    def _connection(self):
        cr = sql_db.db_connect(self.env.cr.dbname).cursor()
        self.addCleanup(cr.close)
        return cr

    def test_locked_row_is_skipped_until_released(self):
        setup = self._connection()
        setup.execute("""
            INSERT INTO nuqtapass_sync (company_id, kind, channel, state, order_ref, dedupe_key, phone, amount,
                                        occurred_at, next_attempt_at, attempts)
            VALUES (%s, 'sale', 'till', 'pending', 'LOCK/1', 'sale|LOCK/1|', '+96891234567', 1,
                    now() at time zone 'utc', now() at time zone 'utc' + interval '3 seconds', 0)
            RETURNING id""", [self.env.company.id])
        row_id = setup.fetchone()[0]
        # Committed so the other connections see it; due only for this test's "now" (+5 s), not for a cron
        # worker of a running Odoo that scans test databases too.
        setup.commit()

        def cleanup():
            setup.rollback()
            setup.execute("DELETE FROM nuqtapass_sync WHERE id = %s", [row_id])
            setup.commit()
        self.addCleanup(cleanup)

        other = self._connection()  # e.g. the till's send-now, mid-request
        other.execute("SELECT id FROM nuqtapass_sync WHERE id = %s FOR UPDATE", [row_id])
        cron = self._connection()
        cron_env = api.Environment(cron, SUPERUSER_ID, {})
        now = fields.Datetime.now() + timedelta(seconds=5)
        with patch.object(NuqtaPassClient, "sale", return_value=ok({"status": "OK"})) as mocked:
            cron_env["nuqtapass.sync"]._send_due(now=now)
            mocked.assert_not_called()
            self.assertEqual(cron_env["nuqtapass.sync"].browse(row_id).attempts, 0)
            cron.rollback()
            other.rollback()  # released: now it can be sent
            cron_env.invalidate_all()
            cron_env["nuqtapass.sync"]._send_due(now=now)
        self.assertEqual(cron_env["nuqtapass.sync"].browse(row_id).attempts, 1)
        cron.rollback()
