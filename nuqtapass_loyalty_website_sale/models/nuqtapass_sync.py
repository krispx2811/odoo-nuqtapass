from odoo import fields, models


class NuqtapassSync(models.Model):
    _inherit = "nuqtapass.sync"

    sale_order_id = fields.Many2one("sale.order", "Online order", index="btree_not_null", readonly=True,
                                    ondelete="set null")
    move_id = fields.Many2one("account.move", "Credit note", index="btree_not_null", readonly=True,
                              ondelete="set null")
