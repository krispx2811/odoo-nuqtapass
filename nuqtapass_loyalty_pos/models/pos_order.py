import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class PosOrder(models.Model):
    _inherit = "pos.order"

    nuqtapass_phone = fields.Char(
        "NuqtaPass phone", copy=False,
        help="Phone typed in the NuqtaPass window on the till; used before the customer's own phone.",
    )
    nuqtapass_sync_ids = fields.One2many("nuqtapass.sync", "pos_order_id", "NuqtaPass sync")
    nuqtapass_status = fields.Char("NuqtaPass", compute="_compute_nuqtapass_status")

    @api.depends("nuqtapass_sync_ids.summary")
    def _compute_nuqtapass_status(self):
        for order in self:
            order.nuqtapass_status = order.nuqtapass_sync_ids[:1].summary or False

    def action_pos_order_paid(self):
        result = super().action_pos_order_paid()
        self._nuqtapass_queue()
        return result

    def _nuqtapass_raw_phone(self):
        return self.nuqtapass_phone or self.partner_id.phone

    def _nuqtapass_queue(self):
        for order in self:
            try:
                order._nuqtapass_queue_one()
            except Exception:  # a till sale must never fail because of NuqtaPass
                _logger.exception("NuqtaPass: could not queue POS order %s", order.id)

    def _nuqtapass_queue_one(self):
        self.ensure_one()
        Sync = self.env["nuqtapass.sync"].sudo()
        if not Sync._channel_enabled("till"):
            return
        currency = self.currency_id
        if self.is_refund or currency.compare_amounts(self.amount_total, 0) < 0:
            original = self.refunded_order_id
            sale = original and Sync.search(
                [("kind", "=", "sale"), ("pos_order_id", "=", original.id)], limit=1)
            if not sale:
                return  # the original never earned, so there is nothing to take back
            Sync._queue({
                "kind": "refund",
                "channel": "till",
                "order_ref": sale.order_ref,
                # The refund's own receipt number: partial refunds all share the name "<order> REFUND".
                "refund_ref": self.pos_reference,
                "phone": sale.phone,
                "amount": abs(self.amount_total),
                "currency_id": currency.id,
                "occurred_at": self.date_order or fields.Datetime.now(),
                "company_id": self.company_id.id,
                "pos_order_id": self.id,
            })
            return
        if currency.compare_amounts(self.amount_total, 0) <= 0:
            return
        phone_vals = Sync._sale_phone_vals(self._nuqtapass_raw_phone(), self.company_id)
        if not phone_vals:
            return
        Sync._queue({
            "kind": "sale",
            "channel": "till",
            # Odoo's receipt number ("266-1-000001": year + device, till, number), not `name`: on Odoo 20 every
            # till device starts its names at "<till> - 000001", so names repeat across devices.
            "order_ref": self.pos_reference,
            **phone_vals,
            "amount": self.amount_total,
            "currency_id": currency.id,
            "occurred_at": self.date_order or fields.Datetime.now(),
            "branch": self.config_id.nuqtapass_branch or False,
            "customer_name": self.partner_id.name or False,
            "company_id": self.company_id.id,
            "pos_order_id": self.id,
        })
