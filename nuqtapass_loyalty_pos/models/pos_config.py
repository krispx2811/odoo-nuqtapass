from odoo import fields, models


class PosConfig(models.Model):
    _inherit = "pos.config"

    nuqtapass_branch = fields.Char(
        "NuqtaPass branch",
        help="Branch id, code or name in NuqtaPass. Empty: NuqtaPass tags the visit 'Odoo'.",
    )
