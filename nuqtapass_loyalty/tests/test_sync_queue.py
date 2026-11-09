from datetime import datetime

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "nuqtapass")
class TestSyncQueue(TransactionCase):
    def setUp(self):
        super().setUp()
        self.Sync = self.env["nuqtapass.sync"].sudo()
        self.env.company.country_id = self.env.ref("base.om")
        self.omr = self.env.ref("base.OMR")
        self.omr.active = True

    def _sale(self, **over):
        vals = {
            "kind": "sale", "channel": "till", "order_ref": "Shop/0001", "phone": "+96891234567",
            "amount": 2.5, "currency_id": self.omr.id, "occurred_at": datetime(2026, 11, 9, 10, 0, 0),
        }
        vals.update(over)
        return self.Sync._queue(vals)

    def test_queue_creates_pending_due_now(self):
        rec = self._sale()
        self.assertEqual(rec.state, "pending")
        self.assertEqual(rec.attempts, 0)
        self.assertTrue(rec.next_attempt_at)
        self.assertEqual(rec.company_id, self.env.company)

    def test_same_order_queued_once(self):
        self.assertEqual(self._sale(), self._sale())
        self.assertEqual(self.Sync.search_count([("order_ref", "=", "Shop/0001")]), 1)

    def test_sale_needs_phone_refund_needs_ref(self):
        with self.assertRaises(ValueError):
            self._sale(phone=False)
        with self.assertRaises(ValueError):
            self.Sync._queue({"kind": "refund", "channel": "till", "order_ref": "Shop/0001",
                              "amount": 1, "occurred_at": datetime(2026, 11, 9)})

    def test_sale_payload_uses_spec_field_names(self):
        rec = self._sale(branch="Qurum", customer_name="Sara", amount=2.5004)
        self.assertEqual(rec._payload(), {
            "source": "odoo", "channel": "till", "orderRef": "Shop/0001", "phone": "+96891234567",
            "amount": 2.5, "paidAt": "2026-11-09T10:00:00Z", "branch": "Qurum", "customerName": "Sara",
        })

    def test_sale_payload_omits_empty_optionals(self):
        self.assertNotIn("branch", self._sale()._payload())
        self.assertNotIn("customerName", self._sale(order_ref="Shop/0002")._payload())

    def test_refund_payload(self):
        rec = self.Sync._queue({
            "kind": "refund", "channel": "online", "order_ref": "S00042", "refund_ref": "RINV/2026/0001",
            "amount": 4.0, "order_amount": 10.0, "currency_id": self.omr.id,
            "occurred_at": datetime(2026, 11, 9, 12, 30),
        })
        self.assertEqual(rec._payload(), {
            "source": "odoo", "orderRef": "S00042", "refundRef": "RINV/2026/0001",
            "amount": 4.0, "refundedAt": "2026-11-09T12:30:00Z", "orderAmount": 10.0, "returnUses": {},
        })

    def test_two_refunds_of_one_order_are_separate(self):
        base = {"kind": "refund", "channel": "till", "order_ref": "Shop/0001", "amount": 1,
                "occurred_at": datetime(2026, 11, 9)}
        a = self.Sync._queue(dict(base, refund_ref="Shop/0001 REFUND #7"))
        b = self.Sync._queue(dict(base, refund_ref="Shop/0001 REFUND #8"))
        self.assertNotEqual(a, b)

    def test_channel_switches(self):
        icp = self.env["ir.config_parameter"].sudo()
        icp.set_bool("nuqtapass_loyalty.till_enabled", True)
        self.assertTrue(self.Sync._channel_enabled("till"))
        icp.set_bool("nuqtapass_loyalty.till_enabled", False)
        self.assertFalse(self.Sync._channel_enabled("till"))

    def test_normalise_phone_uses_company_country(self):
        self.assertEqual(self.Sync._normalise_phone("9123 4567", self.env.company), "+96891234567")

    def test_normalise_phone_refuses_a_short_oman_number(self):
        self.assertIsNone(self.Sync._normalise_phone("9417872", self.env.company))

    def test_sale_phone_vals(self):
        company = self.env.company
        self.assertEqual(self.Sync._sale_phone_vals("  ", company), {})
        self.assertEqual(self.Sync._sale_phone_vals(False, company), {})
        self.assertEqual(self.Sync._sale_phone_vals("94176872", company), {"phone": "+96894176872"})
        self.assertEqual(self.Sync._sale_phone_vals(" 9417872 ", company), {"phone": "9417872", "phone_invalid": True})

    def test_wrong_phone_is_logged_failed_and_never_due(self):
        rec = self._sale(phone="9417872", phone_invalid=True)
        self.assertEqual(rec.state, "failed")
        self.assertFalse(rec.next_attempt_at)
        self.assertEqual(rec.summary, "Phone number looks wrong: 9417872")
        self.assertFalse(self.Sync._due(datetime(2030, 1, 1)))
