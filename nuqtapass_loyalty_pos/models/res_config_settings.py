from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    pos_nuqtapass_branch = fields.Char(related="pos_config_id.nuqtapass_branch", readonly=False)
