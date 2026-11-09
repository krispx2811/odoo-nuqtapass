import json
import logging
import math

from odoo import api, fields, models

_logger = logging.getLogger(__name__)
PAID_STATES = ("paid", "done", "invoiced")
CUSTOMER_FIELDS = {"partner_id", "nuqtapass_phone"}


class PosOrder(models.Model):
    _inherit = "pos.order"

    nuqtapass_phone = fields.Char(
        "NuqtaPass phone", copy=False,
        help="Phone typed in the NuqtaPass window on the till; used before the customer's own phone.",
    )
    nuqtapass_sync_ids = fields.One2many("nuqtapass.sync", "pos_order_id", "NuqtaPass sync")
    nuqtapass_status = fields.Char("NuqtaPass", compute="_compute_nuqtapass_status")
    nuqtapass_used = fields.Char("Used at NuqtaPass", compute="_compute_nuqtapass_used",
                                 help="What this order used of the customer's NuqtaPass cards when it was paid.")

    @api.depends("nuqtapass_sync_ids.summary")
    def _compute_nuqtapass_status(self):
        for order in self:
            order.nuqtapass_status = order.nuqtapass_sync_ids[:1].summary or False

    def _nuqtapass_uses(self):
        self.ensure_one()
        if not self.pos_reference:
            return self.env["nuqtapass.pos.use"]
        return self.env["nuqtapass.pos.use"].sudo().search(
            [("company_id", "=", self.company_id.id), ("order_ref", "=", self.pos_reference)])

    def _compute_nuqtapass_used(self):
        _ = self.env._
        for order in self:
            parts = []
            for use in order._nuqtapass_uses():
                if use.use == "points":
                    parts.append(_("Points used: %(n)s", n=use.quantity))
                elif use.use == "credit":
                    parts.append(_("Credit used: %(n)s", n=round(use.amount, 3)))
                elif use.use == "pack":
                    parts.append(_("Pack uses used: %(n)s", n=use.quantity))
                elif use.use == "reward":
                    parts.append(_("Stamp reward used"))
                else:
                    parts.append(_("Voucher used"))
            order.nuqtapass_used = " · ".join(str(p) for p in parts) or False

    def action_pos_order_paid(self):
        result = super().action_pos_order_paid()
        self._nuqtapass_queue()
        return result

    def write(self, vals):
        result = super().write(vals)
        # A paid order earns as soon as it gets a customer: on the receipt screen, from the back office, or when the
        # till sends the order again with a customer. The queue's de-dup key keeps it to one sale per order.
        if CUSTOMER_FIELDS & vals.keys():
            self.filtered(lambda o: o.state in PAID_STATES)._nuqtapass_customer_changed()
        return result

    def _nuqtapass_customer_changed(self):
        for order in self:
            try:
                sale = order.nuqtapass_sync_ids.filtered(lambda s: s.kind == "sale")[:1]
                if not sale:
                    order._nuqtapass_queue_one()
                elif sale.state == "failed" and sale.phone_invalid:
                    sale.action_resend()  # logged with a wrong phone: check the new one (a good one is sent)
            except Exception:  # saving the order must never fail because of NuqtaPass
                _logger.exception("NuqtaPass: could not queue POS order %s after its customer changed", order.id)

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
            self._nuqtapass_queue_refund(Sync)
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

    # ── refunds ───────────────────────────────────────────────────────
    def _nuqtapass_queue_refund(self, Sync):
        """Queue this refund against the original order, when that order earned or used something at NuqtaPass.

        Always sends the whole order's amount (`orderAmount`) and what the refunded lines gave back of its uses at
        payment (`returnUses`); `amount` is the money given back, 0 when only NuqtaPass lines were refunded.
        """
        currency = self.currency_id
        original = self.refunded_order_id
        if not original:
            return
        sale = Sync.search([("kind", "=", "sale"), ("pos_order_id", "=", original.id)], limit=1)
        uses = original._nuqtapass_uses()
        if not sale and not uses:
            return  # the original never earned nor used anything, so there is nothing to take or give back
        returned = self._nuqtapass_return_uses()
        amount = max(0.0, -self.amount_total)
        if currency.is_zero(amount) and not returned:
            return
        Sync._queue({
            "kind": "refund",
            "channel": "till",
            "order_ref": sale.order_ref if sale else original.pos_reference,
            # The refund's own receipt number: partial refunds all share the name "<order> REFUND".
            "refund_ref": self.pos_reference,
            "phone": sale.phone if sale else uses[:1].phone,
            "amount": 0.0 if currency.is_zero(amount) else amount,
            "order_amount": original.amount_total,
            "return_uses": json.dumps(returned),
            "currency_id": currency.id,
            "occurred_at": self.date_order or fields.Datetime.now(),
            "company_id": self.company_id.id,
            "pos_order_id": self.id,
        })

    def _nuqtapass_return_uses(self):
        """Part 1 `returnUses` from this refund's lines and payments: the share of each refunded NuqtaPass line
        (points and pack uses rounded down), a refunded reward, the refunded vouchers' cards, the credit paid back."""
        returned = {}
        vouchers = []
        for line in self.lines:
            origin = line.refunded_orderline_id
            if not origin.nuqtapass_use or not origin.qty:
                continue
            share = min(1.0, abs(line.qty) / abs(origin.qty))
            if origin.nuqtapass_use in ("points", "pack"):
                n = math.floor(origin.nuqtapass_qty * share + 1e-9)
                if n:
                    returned[origin.nuqtapass_use] = returned.get(origin.nuqtapass_use, 0) + n
            elif origin.nuqtapass_use == "reward":
                returned["reward"] = True
            elif origin.nuqtapass_card_id and origin.nuqtapass_card_id not in vouchers:
                vouchers.append(origin.nuqtapass_card_id)
        if vouchers:
            returned["vouchers"] = vouchers
        credit = -sum(self.payment_ids.filtered(lambda p: p.payment_method_id.nuqtapass_credit).mapped("amount"))
        if credit > 0:
            returned["credit"] = round(credit, 3)
        return returned
