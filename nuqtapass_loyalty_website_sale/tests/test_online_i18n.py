from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "nuqtapass")
class TestOnlineArabic(TransactionCase):
    def test_website_branch_setting_in_arabic(self):
        self.env["res.lang"]._activate_lang("ar_001")
        self.env["ir.module.module"]._load_module_terms(["nuqtapass_loyalty_website_sale"], ["ar_001"], overwrite=True)
        arch = self.env["res.config.settings"].with_context(lang="ar_001").get_view(view_type="form")["arch"]
        self.assertIn("فرع NuqtaPass", arch)
        self.assertIn("طلبات هالموقع", arch)
