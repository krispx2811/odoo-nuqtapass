from odoo import fields, models


class NuqtapassSync(models.Model):
    _inherit = "nuqtapass.sync"

    pos_order_id = fields.Many2one("pos.order", "Till order", index="btree_not_null", readonly=True,
                                   ondelete="set null")

    def _nuqtapass_current_phone(self):
        if self.kind == "sale" and self.pos_order_id:
            return self.pos_order_id._nuqtapass_raw_phone()
        return super()._nuqtapass_current_phone()
