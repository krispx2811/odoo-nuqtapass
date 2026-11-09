from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "nuqtapass")
class TestPosArabic(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["res.lang"]._activate_lang("ar_001")
        cls.env["ir.module.module"]._load_module_terms(
            ["nuqtapass_loyalty", "nuqtapass_loyalty_pos"], ["ar_001"], overwrite=True)
        cls.env["ir.config_parameter"].sudo().set_bool("nuqtapass_loyalty.till_enabled", True)
        cls.config = cls.env["pos.config"].create({"name": "Till AR"})

    def test_till_message_in_arabic(self):
        config = self.config.with_context(lang="ar_001")
        _client, error = config._nuqtapass_prepare("12")
        self.assertEqual(error["message"], "رقم الجوال شكله غلط: 12")

    def test_order_tab_in_arabic(self):
        arch = self.env["pos.order"].with_context(lang="ar_001").get_view(view_type="form")["arch"]
        self.assertIn("أعد الإرسال", arch)
