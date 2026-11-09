from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    pos_nuqtapass_branch = fields.Char(related="pos_config_id.nuqtapass_branch", readonly=False)

    def set_values(self):
        super().set_values()
        # The till switch turned on: every company with a till gets the "NuqtaPass credit" payment method.
        if self.env["nuqtapass.sync"].sudo()._channel_enabled("till"):
            self.env["pos.payment.method"]._nuqtapass_ensure_all()
