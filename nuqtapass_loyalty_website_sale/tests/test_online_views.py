from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "nuqtapass")
class TestOnlineViews(TransactionCase):
    def _arch(self, model, view_type="form"):
        return self.env[model].get_view(view_type=view_type)["arch"]

    def test_sale_order_form_has_nuqtapass_tab(self):
        arch = self._arch("sale.order")
        self.assertIn('name="nuqtapass_sync_ids"', arch)
        self.assertIn("action_resend", arch)

    def test_website_settings_have_branch_once(self):
        self.assertEqual(self._arch("res.config.settings").count('name="website_nuqtapass_branch"'), 1)

    def test_sync_form_links_order_and_credit_note(self):
        arch = self._arch("nuqtapass.sync")
        self.assertIn('name="sale_order_id"', arch)
        self.assertIn('name="move_id"', arch)

    def test_log_menu_under_ecommerce_orders(self):
        menu = self.env.ref("nuqtapass_loyalty_website_sale.menu_nuqtapass_sync_website")
        self.assertEqual(menu.parent_id, self.env.ref("website_sale.menu_orders"))
        self.assertEqual(menu.action, self.env.ref("nuqtapass_loyalty.action_nuqtapass_sync"))
