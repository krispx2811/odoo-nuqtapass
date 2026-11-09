from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from odoo.addons.nuqtapass_loyalty.lib.client import ApiResult, NuqtaPassClient


@tagged("post_install", "-at_install", "nuqtapass")
class TestSettings(TransactionCase):
    def _settings(self, **vals):
        return self.env["res.config.settings"].create(vals)

    def test_key_saved_in_system_parameter(self):
        self._settings(nuqtapass_api_key="sip_abc").execute()
        self.assertEqual(self.env["ir.config_parameter"].sudo().get_str("nuqtapass_loyalty.api_key"), "sip_abc")

    def test_switches_round_trip(self):
        self._settings(nuqtapass_till_enabled=False, nuqtapass_online_enabled=True).execute()
        Sync = self.env["nuqtapass.sync"]
        self.assertFalse(Sync._channel_enabled("till"))
        self.assertTrue(Sync._channel_enabled("online"))

    def test_switches_on_after_install(self):
        settings = self._settings()
        self.assertTrue(settings.nuqtapass_till_enabled)
        self.assertTrue(settings.nuqtapass_online_enabled)

    def test_test_connection_uses_typed_key_and_shows_shop(self):
        result = ApiResult(True, 200, {"shop": {"name": "Demo Café"}}, None, None, False)
        with patch.object(NuqtaPassClient, "ping", return_value=result) as ping:
            action = self._settings(nuqtapass_api_key="sip_typed").action_nuqtapass_test_connection()
        ping.assert_called_once()
        self.assertEqual(action["params"]["type"], "success")
        self.assertIn("Demo Café", action["params"]["message"])
        # Testing never saves the key.
        self.assertFalse(self.env["ir.config_parameter"].sudo().get_str("nuqtapass_loyalty.api_key"))

    def test_test_connection_error(self):
        result = ApiResult(False, 401, None, "Invalid key", "UNAUTHORIZED", True)
        with patch.object(NuqtaPassClient, "ping", return_value=result):
            action = self._settings(nuqtapass_api_key="sip_bad").action_nuqtapass_test_connection()
        self.assertEqual(action["params"]["type"], "danger")
        self.assertIn("Invalid key", action["params"]["message"])

    def test_test_connection_without_key(self):
        with patch.object(NuqtaPassClient, "ping") as ping:
            action = self._settings(nuqtapass_api_key=False).action_nuqtapass_test_connection()
        ping.assert_not_called()
        self.assertEqual(action["params"]["type"], "warning")

    def test_test_connection_bad_base_url_setting(self):
        self.env["ir.config_parameter"].sudo().set_str("nuqtapass_loyalty.base_url", "http://insecure.example")
        with patch.object(NuqtaPassClient, "ping") as ping:
            action = self._settings(nuqtapass_api_key="sip_typed").action_nuqtapass_test_connection()
        ping.assert_not_called()
        self.assertEqual(action["params"]["type"], "danger")

    def test_sync_log_action_and_views_load(self):
        action = self.env.ref("nuqtapass_loyalty.action_nuqtapass_sync")
        self.assertEqual(action.res_model, "nuqtapass.sync")
        Sync = self.env["nuqtapass.sync"]
        for view_type in ("list", "form", "search"):
            self.assertTrue(Sync.get_view(view_type=view_type)["arch"])

    def test_settings_page_has_nuqtapass_app(self):
        arch = self.env["res.config.settings"].get_view(view_type="form")["arch"]
        self.assertIn('name="nuqtapass_loyalty"', arch)
        self.assertIn("nuqtapass_api_key", arch)
        self.assertIn("action_nuqtapass_test_connection", arch)
