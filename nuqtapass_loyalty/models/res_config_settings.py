from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # Odoo 19 stores these with set_param: a Boolean switched on is "True", switched off deletes the parameter.
    nuqtapass_api_key = fields.Char("NuqtaPass key", config_parameter="nuqtapass_loyalty.api_key")
    nuqtapass_till_enabled = fields.Boolean("Earn at the till", config_parameter="nuqtapass_loyalty.till_enabled")
    nuqtapass_online_enabled = fields.Boolean(
        "Earn in the online store", config_parameter="nuqtapass_loyalty.online_enabled")

    def _nuqtapass_notify(self, kind, message):
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": "NuqtaPass", "message": message, "type": kind, "sticky": False},
        }

    def action_nuqtapass_test_connection(self):
        """Uses the key typed on the page, saved or not."""
        self.ensure_one()
        _ = self.env._
        key = (self.nuqtapass_api_key or "").strip()
        if not key:
            return self._nuqtapass_notify("warning", _("Paste your NuqtaPass key first."))
        try:
            client = self.env["nuqtapass.sync"]._make_client(key)
        except ValueError:
            return self._nuqtapass_notify("danger", _("Could not connect: the NuqtaPass address setting is wrong."))
        result = client.ping()
        if result.ok:
            shop = ((result.data or {}).get("shop") or {}).get("name") or "?"
            return self._nuqtapass_notify("success", _("Connected to %(shop)s.", shop=shop))
        return self._nuqtapass_notify("danger", _("Could not connect: %(error)s", error=result.error))
