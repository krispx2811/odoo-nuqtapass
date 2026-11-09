import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    def _post(self, soft=True):
        posted = super()._post(soft)
        posted.filtered(lambda m: m.move_type == "out_refund")._nuqtapass_queue_refund()
        return posted

    def _nuqtapass_queue_refund(self):
        Sync = self.env["nuqtapass.sync"].sudo()
        if not Sync._channel_enabled("online"):
            return
        for move in self.sudo():
            try:
                # sale_line_ids is copy=False, so a reversal may not carry it: also look through the invoice.
                orders = (move.invoice_line_ids.sale_line_ids.order_id
                          | move.reversed_entry_id.invoice_line_ids.sale_line_ids.order_id)
                order = orders.filtered("website_id")[:1]
                sale = order and order.nuqtapass_sync_ids.filtered(lambda s: s.kind == "sale")[:1]
                if not sale:
                    continue
                Sync._queue({
                    "kind": "refund",
                    "channel": "online",
                    "order_ref": sale.order_ref,  # the original order's "S00023#57"
                    # The credit note's own number (e.g. "RINV/2026/00001"): unique per posted journal entry.
                    "refund_ref": move.name,
                    "phone": sale.phone,
                    "amount": move.amount_total,
                    "currency_id": move.currency_id.id,
                    "occurred_at": fields.Datetime.now(),
                    "company_id": move.company_id.id,
                    "sale_order_id": order.id,
                    "move_id": move.id,
                })
            except Exception:  # a credit note must never fail because of NuqtaPass
                _logger.exception("NuqtaPass: could not queue credit note %s", move.id)
