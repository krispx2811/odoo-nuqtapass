from odoo import fields, models


class NuqtapassSync(models.Model):
    _inherit = "nuqtapass.sync"

    pos_order_id = fields.Many2one("pos.order", "Till order", index="btree_not_null", readonly=True,
                                   ondelete="set null")
