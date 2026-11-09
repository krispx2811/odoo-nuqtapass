from odoo import api, fields, models

LINE_USES = [("points", "NuqtaPass points"), ("pack", "Service pack"), ("reward", "Stamp reward"),
             ("voucher", "Voucher")]


class PosOrderLine(models.Model):
    _inherit = "pos.order.line"

    # Set by the till on its NuqtaPass lines; refunds read them to give back what the refunded lines used.
    nuqtapass_use = fields.Selection(LINE_USES, "NuqtaPass use", copy=False)
    nuqtapass_card_id = fields.Char("NuqtaPass card", copy=False)
    nuqtapass_voucher_id = fields.Char("NuqtaPass voucher", copy=False)
    nuqtapass_qty = fields.Integer("NuqtaPass points / uses", copy=False)

    @api.model
    def _load_pos_data_fields(self, config):
        return super()._load_pos_data_fields(config) + [
            "nuqtapass_use", "nuqtapass_card_id", "nuqtapass_voucher_id", "nuqtapass_qty"]
