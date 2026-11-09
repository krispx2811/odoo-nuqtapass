"""A paid till order earns once, as soon as it has a valid customer phone, whenever that happens."""
from odoo.tests import tagged

from odoo.addons.point_of_sale.tests.common import TestPoSCommon


@tagged("post_install", "-at_install", "nuqtapass")
class TestPosLateCustomer(TestPoSCommon):
    def setUp(self):
        super().setUp()
        self.config = self.basic_config
        self.env.company.country_id = self.env.ref("base.om")
        icp = self.env["ir.config_parameter"].sudo()
        icp.set_bool("nuqtapass_loyalty.till_enabled", True)
        icp.set_str("nuqtapass_loyalty.api_key", "sip_test")
        self.product = self.create_product("Coffee", self.categ_basic, 2.5, 1.0)
        self.customer.phone = "9123 4567"
        self.other_customer.phone = "9876 5432"
        self.Sync = self.env["nuqtapass.sync"].sudo()
        self.open_new_session()

    def _data(self, customer=None, **ui_args):
        return self.create_ui_order_data([(self.product, 1)], ui_args, customer=customer)

    def _sync(self, data):
        res = self.env["pos.order"].sync_from_ui([data])
        return self.env["pos.order"].browse(res["pos.order"][0]["id"])

    def _sales(self, order):
        return self.Sync.search([("kind", "=", "sale"), ("pos_order_id", "=", order.id)])

    def test_paid_without_customer_earns_when_the_customer_is_set_in_the_back_office(self):
        order = self._sync(self._data())
        self.assertFalse(self._sales(order))
        order.partner_id = self.customer
        sale = self._sales(order)
        self.assertEqual((len(sale), sale.phone, sale.order_ref), (1, "+96891234567", order.pos_reference))
        self.assertEqual(sale.customer_name, self.customer.name)

    def test_paid_without_customer_earns_when_a_phone_is_typed_later(self):
        order = self._sync(self._data())
        order.nuqtapass_phone = "9876 5432"
        self.assertEqual(self._sales(order).phone, "+96898765432")

    def test_paid_without_customer_earns_when_the_till_sends_the_customer_after_payment(self):
        data = self._data()
        order = self._sync(data)
        # The till sends a paid order again when the customer is changed after payment (Odoo: process_saved_payments).
        self._sync(dict(data, partner_id=self.customer.id))
        self.assertEqual(order.partner_id, self.customer)
        self.assertEqual(self._sales(order).phone, "+96891234567")

    def test_later_changes_never_queue_twice(self):
        order = self._sync(self._data())
        order.partner_id = self.customer
        order.nuqtapass_phone = "9876 5432"
        order.partner_id = self.other_customer
        sale = self._sales(order)
        self.assertEqual((len(sale), sale.phone), (1, "+96891234567"))

    def test_paid_with_customer_then_changed_still_one_row(self):
        order = self._sync(self._data(customer=self.customer))
        order.partner_id = self.other_customer
        self.assertEqual(len(self._sales(order)), 1)

    def test_customer_without_a_phone_queues_nothing(self):
        self.other_customer.phone = False
        order = self._sync(self._data())
        order.partner_id = self.other_customer
        self.assertFalse(self._sales(order))

    def test_unpaid_order_waits_for_payment(self):
        order = self._sync(self._data(state="draft"))
        self.assertEqual(order.state, "draft")
        order.partner_id = self.customer
        self.assertFalse(self._sales(order))

    def test_till_switched_off_queues_nothing(self):
        order = self._sync(self._data())
        self.env["ir.config_parameter"].sudo().set_bool("nuqtapass_loyalty.till_enabled", False)
        order.partner_id = self.customer
        self.assertFalse(self._sales(order))

    def test_wrong_phone_row_is_checked_again_when_a_good_phone_arrives(self):
        self.customer.phone = "9417872"  # an Omani mobile missing a digit
        order = self._sync(self._data(customer=self.customer))
        sale = self._sales(order)
        self.assertEqual((sale.state, sale.phone_invalid), ("failed", True))
        order.nuqtapass_phone = "9417 6872"
        self.assertEqual((sale.state, sale.phone, sale.phone_invalid), ("pending", "+96894176872", False))
        self.assertEqual(len(self._sales(order)), 1)

    def test_customer_change_on_a_refund_adds_no_row(self):
        order = self._sync(self._data(customer=self.customer))
        refund = self.env["pos.order"].browse(order.refund()["res_id"])
        self.make_payment(refund, self.cash_pm1, refund.amount_total)
        before = self.Sync.search_count([])
        refund.partner_id = self.other_customer
        self.assertEqual(self.Sync.search_count([]), before)
