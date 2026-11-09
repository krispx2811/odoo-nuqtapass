from odoo import fields, models


class PosPayment(models.Model):
    _inherit = "pos.payment"

    # A "NuqtaPass credit" payment: the prepaid card it is spent from (set by the till's NuqtaPass panel).
    nuqtapass_card_id = fields.Char("NuqtaPass card", copy=False)
