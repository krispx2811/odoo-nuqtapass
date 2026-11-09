from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    website_nuqtapass_branch = fields.Char(
        "NuqtaPass branch (online store)", related="website_id.nuqtapass_branch", readonly=False)
