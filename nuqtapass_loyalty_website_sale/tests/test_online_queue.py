from datetime import timedelta

from odoo import Command, fields
from odoo.tests import tagged
from odoo.tools import mute_logger

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.account_payment.tests.common import AccountPaymentCommon


def _setup_shop(env):
    env.company.country_id = env.ref("base.om")
    # Odoo 19: get_param / set_param (Odoo 20 replaced them with typed calls).
    icp = env["ir.config_parameter"].sudo()
    icp.set_param("nuqtapass_loyalty.online_enabled", "True")
    icp.set_param("nuqtapass_loyalty_website_sale.since",
                fields.Datetime.to_string(fields.Datetime.now() - timedelta(days=1)))
    website = env["website"].create({"name": "Shop site", "nuqtapass_branch": "Online"})
    env.user.group_ids |= env.ref("sales_team.group_sale_manager")
    partner = env["res.partner"].create({"name": "Sara", "phone": "9123 4567"})
    product = env["product.product"].create({
        "name": "Mug", "list_price": 10.0, "invoice_policy": "order", "taxes_id": [Command.clear()],
    })
    return website, partner, product


@tagged("post_install", "-at_install", "nuqtapass")
class TestOnlineByInvoice(AccountTestInvoicingCommon):
    def setUp(self):
        super().setUp()
        self.website, self.partner, self.product = _setup_shop(self.env)
        self.Sync = self.env["nuqtapass.sync"].sudo()

    def _order(self, website=True):
        order = self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "website_id": self.website.id if website else False,
            "order_line": [Command.create({"product_id": self.product.id, "product_uom_qty": 1, "price_unit": 10.0})],
        })
        order.action_confirm()
        return order

    def _invoice_and_pay(self, order):
        invoice = order._create_invoices()
        invoice.action_post()
        self.env["account.payment.register"].with_context(
            active_model="account.move", active_ids=invoice.ids).create({})._create_payments()
        return invoice

    def _credit_note(self, invoice):
        credit = invoice._reverse_moves()
        credit.action_post()
        return credit

    def test_install_hook_sets_since(self):
        self.assertTrue(self.env["ir.config_parameter"].sudo().get_param("nuqtapass_loyalty_website_sale.since"))

    def test_unpaid_order_not_queued(self):
        order = self._order()
        self.env["sale.order"]._cron_nuqtapass_scan()
        self.assertFalse(order.nuqtapass_sync_ids)

    def test_paid_invoice_queues_sale_once(self):
        order = self._order()
        self._invoice_and_pay(order)
        self.assertTrue(order._nuqtapass_is_fully_paid())
        self.env["sale.order"]._cron_nuqtapass_scan()
        self.env["sale.order"]._cron_nuqtapass_scan()
        sync = order.nuqtapass_sync_ids
        self.assertEqual(len(sync), 1)
        # "<name>#<id>" (e.g. "S00023#57"): the name alone is not unique by constraint (risk 13).
        self.assertEqual((sync.kind, sync.channel, sync.order_ref), ("sale", "online", f"{order.name}#{order.id}"))
        self.assertEqual(sync.phone, "+96891234567")
        self.assertEqual(sync.amount, order.amount_total)
        self.assertEqual(sync.branch, "Online")
        self.assertEqual(sync.customer_name, "Sara")
        self.assertEqual(order.nuqtapass_status, sync.summary)

    def test_two_orders_get_distinct_refs(self):
        first, second = self._order(), self._order()
        self._invoice_and_pay(first)
        self._invoice_and_pay(second)
        self.env["sale.order"]._cron_nuqtapass_scan()
        self.assertNotEqual(first.name, second.name)
        self.assertEqual(first.nuqtapass_sync_ids.order_ref, f"{first.name}#{first.id}")
        self.assertEqual(second.nuqtapass_sync_ids.order_ref, f"{second.name}#{second.id}")

    def test_two_orders_renamed_alike_both_queue(self):
        first, second = self._order(), self._order()
        first.name = second.name = "S-SAME"
        self._invoice_and_pay(first)
        self._invoice_and_pay(second)
        self.env["sale.order"]._cron_nuqtapass_scan()
        refs = (first.nuqtapass_sync_ids.order_ref, second.nuqtapass_sync_ids.order_ref)
        self.assertEqual(refs, (f"S-SAME#{first.id}", f"S-SAME#{second.id}"))

    def test_order_without_phone_not_queued(self):
        self.partner.phone = False
        order = self._order()
        self._invoice_and_pay(order)
        self.env["sale.order"]._cron_nuqtapass_scan()
        self.assertFalse(order.nuqtapass_sync_ids)

    def test_order_not_from_website_ignored(self):
        order = self._order(website=False)
        self._invoice_and_pay(order)
        self.env["sale.order"]._cron_nuqtapass_scan()
        self.assertFalse(order.nuqtapass_sync_ids)

    def test_orders_before_install_ignored(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "nuqtapass_loyalty_website_sale.since",
            fields.Datetime.to_string(fields.Datetime.now() + timedelta(hours=1)))
        order = self._order()
        self._invoice_and_pay(order)
        self.env["sale.order"]._cron_nuqtapass_scan()
        self.assertFalse(order.nuqtapass_sync_ids)

    def test_online_switch_off(self):
        self.env["ir.config_parameter"].sudo().set_param("nuqtapass_loyalty.online_enabled", False)
        order = self._order()
        self._invoice_and_pay(order)
        self.env["sale.order"]._cron_nuqtapass_scan()
        self.assertFalse(order.nuqtapass_sync_ids)

    def test_posted_credit_note_queues_refund(self):
        order = self._order()
        invoice = self._invoice_and_pay(order)
        self.env["sale.order"]._cron_nuqtapass_scan()
        credit = self._credit_note(invoice)
        self.assertEqual(credit.move_type, "out_refund")
        refund = self.Sync.search([("kind", "=", "refund"), ("move_id", "=", credit.id)])
        self.assertEqual(len(refund), 1)
        self.assertEqual(refund.channel, "online")
        self.assertEqual(refund.order_ref, f"{order.name}#{order.id}")
        self.assertEqual(refund.refund_ref, credit.name)
        self.assertEqual(refund.phone, "+96891234567")
        self.assertEqual(refund.amount, credit.amount_total)
        payload = refund._payload()
        self.assertEqual((payload["orderRef"], payload["refundRef"]), (f"{order.name}#{order.id}", credit.name))

    def test_two_credit_notes_queue_separately(self):
        order = self._order()
        invoice = self._invoice_and_pay(order)
        self.env["sale.order"]._cron_nuqtapass_scan()
        first, second = self._credit_note(invoice), self._credit_note(invoice)
        refunds = self.Sync.search([("kind", "=", "refund"), ("sale_order_id", "=", order.id)])
        self.assertEqual(sorted(refunds.mapped("refund_ref")), sorted([first.name, second.name]))

    def test_credit_note_for_order_never_sent_ignored(self):
        order = self._order()
        invoice = self._invoice_and_pay(order)  # no scan → no sale row
        credit = self._credit_note(invoice)
        self.assertFalse(self.Sync.search([("move_id", "=", credit.id)]))

    def test_queue_error_never_breaks_credit_note(self):
        order = self._order()
        invoice = self._invoice_and_pay(order)
        self.env["sale.order"]._cron_nuqtapass_scan()

        def boom(*args, **kwargs):
            raise RuntimeError("boom")

        self.patch(type(self.Sync), "_queue", boom)
        with mute_logger("odoo.addons.nuqtapass_loyalty_website_sale.models.account_move"):
            credit = self._credit_note(invoice)
        self.assertEqual(credit.state, "posted")

    def test_branch_editable_from_settings(self):
        settings = self.env["res.config.settings"].create({"website_id": self.website.id})
        self.assertEqual(settings.website_nuqtapass_branch, "Online")
        settings.website_nuqtapass_branch = "Muscat online"
        self.assertEqual(self.website.nuqtapass_branch, "Muscat online")


@tagged("post_install", "-at_install", "nuqtapass")
class TestOnlineByTransaction(AccountPaymentCommon):
    # AccountPaymentCommon = PaymentCommon + accounting, with the `_post_process` mock switched off
    # (`enable_post_process_patcher = False`, Odoo 19), so the real post-processing (confirm the quotation,
    # create the payment) runs.

    def test_done_transaction_queues_sale_when_post_processed(self):
        website, partner, product = _setup_shop(self.env)
        order = self.env["sale.order"].create({
            "partner_id": partner.id,
            "website_id": website.id,
            "order_line": [Command.create({"product_id": product.id, "product_uom_qty": 1, "price_unit": 10.0})],
        })
        tx = self._create_transaction(
            "redirect", sale_order_ids=[order.id], state="done", amount=order.amount_total,
            currency_id=order.currency_id.id, partner_id=partner.id)
        # Odoo 19 has no `_run_post_processing` test helper (and its cron commits), so post-process the
        # transaction directly: `sale` confirms the quotation, then our hook queues the sale.
        tx._post_process()
        self.assertEqual(order.state, "sale")
        self.assertTrue(order._nuqtapass_is_fully_paid())
        sync = order.nuqtapass_sync_ids
        self.assertEqual(len(sync), 1)
        self.assertEqual((sync.kind, sync.channel, sync.order_ref), ("sale", "online", f"{order.name}#{order.id}"))


@tagged("post_install", "-at_install", "nuqtapass")
class TestOnlineWrongPhone(AccountTestInvoicingCommon):
    def test_wrong_phone_logged_not_sent(self):
        website, partner, product = _setup_shop(self.env)
        partner.phone = "9417872"
        order = self.env["sale.order"].create({
            "partner_id": partner.id, "website_id": website.id,
            "order_line": [Command.create({"product_id": product.id, "product_uom_qty": 1, "price_unit": 10.0})],
        })
        order.action_confirm()
        invoice = order._create_invoices()
        invoice.action_post()
        self.env["account.payment.register"].with_context(
            active_model="account.move", active_ids=invoice.ids).create({})._create_payments()
        self.env["sale.order"]._cron_nuqtapass_scan()
        self.env["sale.order"]._cron_nuqtapass_scan()
        sync = order.nuqtapass_sync_ids
        self.assertEqual((len(sync), sync.state, sync.phone), (1, "failed", "9417872"))
        self.assertEqual(order.nuqtapass_status, "Phone number looks wrong: 9417872")
