from odoo import fields, models


class Website(models.Model):
    _inherit = "website"

    nuqtapass_branch = fields.Char(
        "NuqtaPass branch",
        help="Branch id, code or name in NuqtaPass. Empty: NuqtaPass tags the visit 'Odoo online'.",
    )
