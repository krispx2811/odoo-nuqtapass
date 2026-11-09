from odoo import fields, models

USES = [("points", "Points"), ("credit", "Prepaid credit"), ("pack", "Service pack"), ("reward", "Stamp reward"),
        ("voucher", "Voucher")]


class NuqtapassPosUse(models.Model):
    """One use at payment that NuqtaPass recorded for a till order (POST /redeem with its orderRef).

    Written by the spend route at Validate, before the order reaches Odoo, so it is keyed by the order's receipt
    number (pos_reference). Refunds read it for the customer's phone and what each use was.
    """

    _name = "nuqtapass.pos.use"
    _description = "NuqtaPass use at payment"
    _order = "id"
    _rec_name = "order_ref"

    company_id = fields.Many2one("res.company", required=True, index=True, readonly=True)
    config_id = fields.Many2one("pos.config", readonly=True, index=True)
    order_ref = fields.Char("Order", required=True, index=True, readonly=True)
    phone = fields.Char(readonly=True)
    use = fields.Selection(USES, required=True, readonly=True)
    card_id = fields.Char("Card", required=True, readonly=True)
    voucher_id = fields.Char(readonly=True)
    quantity = fields.Integer(help="Points, or pack uses; 1 for a reward or a voucher.", readonly=True)
    amount = fields.Float(help="Money in the shop's NuqtaPass currency: the points' value or the credit used.",
                          digits=(16, 3), readonly=True)
    transaction_id = fields.Char("NuqtaPass transaction", readonly=True)

    _use_unique = models.Constraint(
        "UNIQUE(company_id, order_ref, use, card_id)", "This use is already recorded for this order.")
