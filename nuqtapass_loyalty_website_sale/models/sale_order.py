import logging
from datetime import timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)
SINCE_PARAM = "nuqtapass_loyalty_website_sale.since"


class SaleOrder(models.Model):
    _inherit = "sale.order"

    nuqtapass_sync_ids = fields.One2many("nuqtapass.sync", "sale_order_id", "NuqtaPass sync")
    nuqtapass_status = fields.Char("NuqtaPass", compute="_compute_nuqtapass_status")

    @api.depends("nuqtapass_sync_ids.summary")
    def _compute_nuqtapass_status(self):
        for order in self:
            order.nuqtapass_status = order.nuqtapass_sync_ids[:1].summary or False

    def _nuqtapass_is_fully_paid(self):
        """Website order, confirmed, and paid by done transactions or by paid invoices."""
        self.ensure_one()
        if self.state != "sale" or not self.website_id:
            return False
        currency = self.currency_id
        paid_online = sum(tx.amount for tx in self.transaction_ids if tx.state == "done")
        if currency.compare_amounts(paid_online, self.amount_total) >= 0:
            return True
        invoices = self.invoice_ids.filtered(lambda m: m.move_type == "out_invoice" and m.state == "posted")
        if invoices and all(m.payment_state in ("paid", "in_payment") for m in invoices):
            return currency.compare_amounts(sum(invoices.mapped("amount_total")), self.amount_total) >= 0
        return False

    def _nuqtapass_order_ref(self):
        """"S00023#57": the name is not unique by constraint (editable, per-company sequences), the id is."""
        self.ensure_one()
        return f"{self.name}#{self.id}"

    def _nuqtapass_queue_sale(self):
        Sync = self.env["nuqtapass.sync"].sudo()
        if not Sync._channel_enabled("online"):
            return
        for order in self.sudo():
            try:
                if order.nuqtapass_sync_ids.filtered(lambda s: s.kind == "sale"):
                    continue
                if not order._nuqtapass_is_fully_paid():
                    continue
                phone = Sync._normalise_phone(order.partner_id.phone, order.company_id)
                if not phone:
                    continue
                Sync._queue({
                    "kind": "sale",
                    "channel": "online",
                    "order_ref": order._nuqtapass_order_ref(),
                    "phone": phone,
                    "amount": order.amount_total,
                    "currency_id": order.currency_id.id,
                    "occurred_at": fields.Datetime.now(),
                    "branch": order.website_id.nuqtapass_branch or False,
                    "customer_name": order.partner_id.name or False,
                    "company_id": order.company_id.id,
                    "sale_order_id": order.id,
                })
            except Exception:  # never break payment processing
                _logger.exception("NuqtaPass: could not queue sale order %s", order.id)

    @api.model
    def _cron_nuqtapass_scan(self):
        """Catch orders paid by invoice (bank transfer, manual payment) – every 5 minutes."""
        if not self.env["nuqtapass.sync"]._channel_enabled("online"):
            return
        # Odoo 20: typed get_str (get_param is gone).
        since = self.env["ir.config_parameter"].sudo().get_str(SINCE_PARAM)
        floor = fields.Datetime.now() - timedelta(days=7)
        start = max(fields.Datetime.to_datetime(since), floor) if since else floor
        orders = self.sudo().search([
            ("website_id", "!=", False),
            ("state", "=", "sale"),
            ("date_order", ">=", start),
            ("nuqtapass_sync_ids", "=", False),
        ], limit=500)
        orders._nuqtapass_queue_sale()
