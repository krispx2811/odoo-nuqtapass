from odoo.tests import tagged
from odoo.tools import mute_logger

from odoo.addons.point_of_sale.tests.common import TestPoSCommon


@tagged("post_install", "-at_install", "nuqtapass")
class TestPosQueue(TestPoSCommon):
    def setUp(self):
        super().setUp()
        self.config = self.basic_config
        self.env.company.country_id = self.env.ref("base.om")
        # Odoo 20: typed config parameters (get_param / set_param are gone).
        self.env["ir.config_parameter"].sudo().set_bool("nuqtapass_loyalty.till_enabled", True)
        self.config.nuqtapass_branch = "Qurum"
        self.product = self.create_product("Coffee", self.categ_basic, 2.5, 1.0)
        self.customer.phone = "9123 4567"
        self.Sync = self.env["nuqtapass.sync"].sudo()
        self.open_new_session()

    def _pay(self, customer=None, qty=1, **ui_args):
        data = self.create_ui_order_data([(self.product, qty)], ui_args, customer=customer)
        res = self.env["pos.order"].sync_from_ui([data])
        return self.env["pos.order"].browse(res["pos.order"][0]["id"])

    def _refund(self, order):
        refund = self.env["pos.order"].browse(order.refund()["res_id"])
        self.make_payment(refund, self.cash_pm1, refund.amount_total)
        return refund

    def test_paid_order_with_customer_phone_is_queued(self):
        order = self._pay(customer=self.customer)
        self.assertEqual(order.state, "paid")
        sync = order.nuqtapass_sync_ids
        self.assertEqual(len(sync), 1)
        self.assertEqual((sync.kind, sync.channel), ("sale", "till"))
        self.assertEqual(sync.order_ref, order.name)
        self.assertEqual(sync.phone, "+96891234567")
        self.assertEqual(sync.amount, order.amount_total)
        self.assertEqual(sync.branch, "Qurum")
        self.assertEqual(sync.customer_name, self.customer.name)
        self.assertEqual(sync.state, "pending")
        self.assertEqual(order.nuqtapass_status, sync.summary)

    def test_phone_typed_on_till_wins(self):
        order = self._pay(customer=self.customer, nuqtapass_phone="+971501234567")
        self.assertEqual(order.nuqtapass_sync_ids.phone, "+971501234567")

    def test_phone_typed_on_till_without_customer(self):
        order = self._pay(nuqtapass_phone="9876 5432")
        self.assertEqual(order.nuqtapass_sync_ids.phone, "+96898765432")
        self.assertFalse(order.nuqtapass_sync_ids.customer_name)

    def test_no_branch_on_till_sends_none(self):
        self.config.nuqtapass_branch = False
        self.assertFalse(self._pay(customer=self.customer).nuqtapass_sync_ids.branch)

    def test_no_phone_nothing_queued(self):
        order = self._pay()
        self.assertFalse(order.nuqtapass_sync_ids)

    def test_till_switched_off_nothing_queued(self):
        self.env["ir.config_parameter"].sudo().set_bool("nuqtapass_loyalty.till_enabled", False)
        self.assertFalse(self._pay(customer=self.customer).nuqtapass_sync_ids)

    def test_refund_is_queued_against_original(self):
        order = self._pay(customer=self.customer, qty=2)
        refund = self._refund(order)
        self.assertEqual(refund.state, "paid")
        sync = refund.nuqtapass_sync_ids
        self.assertEqual(len(sync), 1)
        self.assertEqual(sync.kind, "refund")
        self.assertEqual(sync.channel, "till")
        self.assertEqual(sync.order_ref, order.name)
        self.assertEqual(sync.refund_ref, f"{refund.name} #{refund.id}")
        self.assertEqual(sync.phone, "+96891234567")
        self.assertAlmostEqual(sync.amount, abs(refund.amount_total))
        # The sale row stays on the original order.
        self.assertEqual(order.nuqtapass_sync_ids.kind, "sale")

    def test_refund_of_order_never_sent_is_ignored(self):
        order = self._pay()
        self.assertFalse(self._refund(order).nuqtapass_sync_ids)

    def test_queue_error_never_breaks_payment(self):
        def boom(*args, **kwargs):
            raise RuntimeError("boom")

        self.patch(type(self.Sync), "_queue", boom)
        with mute_logger("odoo.addons.nuqtapass_loyalty_pos.models.pos_order"):
            order = self._pay(customer=self.customer)
        self.assertEqual(order.state, "paid")
        self.assertFalse(order.nuqtapass_sync_ids)

    def test_branch_editable_from_pos_settings(self):
        settings = self.env["res.config.settings"].create({"pos_config_id": self.config.id})
        self.assertEqual(settings.pos_nuqtapass_branch, "Qurum")
        settings.pos_nuqtapass_branch = "Seeb"
        self.assertEqual(self.config.nuqtapass_branch, "Seeb")
