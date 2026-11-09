from odoo import fields, models


class NuqtapassSync(models.Model):
    _inherit = "nuqtapass.sync"

    sale_order_id = fields.Many2one("sale.order", "Online order", index="btree_not_null", readonly=True,
                                    ondelete="set null")
    move_id = fields.Many2one("account.move", "Credit note", index="btree_not_null", readonly=True,
                              ondelete="set null")

    def _nuqtapass_current_phone(self):
        if self.kind == "sale" and self.sale_order_id:
            return self.sale_order_id.partner_id.phone
        return super()._nuqtapass_current_phone()
