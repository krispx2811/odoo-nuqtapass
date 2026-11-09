from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "nuqtapass")
class TestPosViews(TransactionCase):
    def _arch(self, model, view_type="form"):
        return self.env[model].get_view(view_type=view_type)["arch"]

    def test_order_form_has_nuqtapass_tab_and_phone(self):
        arch = self._arch("pos.order")
        self.assertIn('name="nuqtapass_sync_ids"', arch)
        self.assertIn('name="nuqtapass_phone"', arch)
        self.assertIn("action_resend", arch)
        # Phones keep "+968…" readable in Arabic: Odoo's phone widget shows them left-to-right.
        self.assertEqual(arch.count('widget="phone"'), 2)

    def test_pos_settings_have_branch(self):
        self.assertIn('name="pos_nuqtapass_branch"', self._arch("res.config.settings"))

    def test_sync_form_links_till_order(self):
        arch = self._arch("nuqtapass.sync")
        self.assertIn('name="pos_order_id"', arch)
        self.assertIn('<field name="phone" widget="phone"', arch)
        self.assertIn('<field name="phone" widget="phone"', self._arch("nuqtapass.sync", "list"))

    def test_log_menu_under_pos_orders(self):
        menu = self.env.ref("nuqtapass_loyalty_pos.menu_nuqtapass_sync_pos")
        self.assertEqual(menu.parent_id, self.env.ref("point_of_sale.menu_point_of_sale"))
        self.assertEqual(menu.action, self.env.ref("nuqtapass_loyalty.action_nuqtapass_sync"))
