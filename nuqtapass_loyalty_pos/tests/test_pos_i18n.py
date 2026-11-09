from unittest.mock import patch

from odoo.tests import TransactionCase, tagged
from odoo.tools.translate import code_translations

from odoo.addons.nuqtapass_loyalty.lib.client import ApiResult, NuqtaPassClient


@tagged("post_install", "-at_install", "nuqtapass")
class TestPosArabic(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["res.lang"]._activate_lang("ar_001")
        cls.env["ir.module.module"]._load_module_terms(
            ["nuqtapass_loyalty", "nuqtapass_loyalty_pos"], ["ar_001"], overwrite=True)
        cls.env["ir.config_parameter"].sudo().set_param("nuqtapass_loyalty.till_enabled", "True")
        cls.config = cls.env["pos.config"].create({"name": "Till AR"})

    def test_till_message_in_arabic(self):
        config = self.config.with_context(lang="ar_001")
        _client, error = config._nuqtapass_prepare("12")
        self.assertEqual(error["message"], "رقم الجوال شكله غلط: 12")

    def test_order_tab_in_arabic(self):
        arch = self.env["pos.order"].with_context(lang="ar_001").get_view(view_type="form")["arch"]
        self.assertIn("أعد الإرسال", arch)

    def test_card_refusal_in_arabic(self):
        config = self.config.with_context(lang="ar_001")
        self.assertEqual(config._nuqtapass_card_refused()["message"], "هالبطاقة مو من هالمحل.")

    # ── uses at payment (2026-11-09) ──────────────────────────────────
    def test_spend_refusals_in_arabic(self):
        self.env["ir.config_parameter"].sudo().set_param("nuqtapass_loyalty.api_key", "sip_test")
        self.env.company.country_id = self.env.ref("base.om")
        config = self.config.with_context(lang="ar_001")
        use = {"use": "points", "card_id": "aaaaaaaa-2222-4222-8222-222222222222", "points": 167,
               "label": "نقاط NuqtaPass"}
        down = ApiResult(False, None, None, "Could not reach NuqtaPass", "NETWORK", True)
        with patch.object(NuqtaPassClient, "redeem", return_value=down):
            res = config._nuqtapass_spend("261-1-000042", "+96891234567", [use])
        self.assertEqual(res["message"], "ما قدرنا نوصل NuqtaPass. شيل بنود NuqtaPass عشان تكمل الدفع بدونها.")
        no = ApiResult(False, 400, None, "ما عنده نقاط كافية", "POINTS_TOO_SMALL", False)
        with patch.object(NuqtaPassClient, "redeem", return_value=no):
            res = config._nuqtapass_spend("261-1-000042", "+96891234567", [use])
        self.assertEqual(res["message"], "نقاط NuqtaPass: ما عنده نقاط كافية. شيل هالبند عشان تكمل الدفع بدونه.")

    def test_till_words_in_arabic(self):
        messages = {m["id"]: m["string"] for m in
                    code_translations.get_web_translations("nuqtapass_loyalty_pos", "ar_001")["messages"]}
        expected = {
            "%(points)s points · worth %(value)s": "%(points)s نقطة · قيمتها %(value)s",
            "= %(points)s points": "= %(points)s نقطة",
            "NuqtaPass points": "نقاط NuqtaPass",
            "Use points": "اصرف النقاط",
            "Use credit": "ادفع من الرصيد",
            "Reward: free %(item)s": "مكافأة: %(item)s مجاناً",
            "Service pack (1 use)": "باقة الخدمات (استخدام واحد)",
            "Remove NuqtaPass lines": "شيل بنود NuqtaPass",
            "Nothing is used until you validate.": "ما ينصرف شي إلا لما تأكد الدفع.",
            # 2026-11-09: tiers, the reward-ready notice, corrections.
            "Gold member · %(pct)s cash-back": "عضو ذهبي · استرداد %(pct)s",
            "Silver member · %(pct)s cash-back": "عضو فضي · استرداد %(pct)s",
            "Bronze member · %(pct)s cash-back": "عضو برونزي · استرداد %(pct)s",
            "%(points)s more points to Gold": "باقي %(points)s نقطة للمستوى الذهبي",
            "Reward ready: %(stamps)s of %(required)s stamps": "المكافأة جاهزة · الأختام: %(stamps)s من %(required)s",
            "Correct": "تصحيح",
            "Undo last stamp": "شيل آخر ختم",
        }
        for english, arabic in expected.items():
            self.assertEqual(messages.get(english), arabic, english)

    def test_credit_method_name_in_arabic(self):
        self.assertEqual(self.env["pos.payment.method"].with_context(lang="ar_001")._fields["nuqtapass_credit"]
                         .get_description(self.env(context={"lang": "ar_001"}))["string"], "رصيد NuqtaPass")

    def test_correction_words_in_arabic(self):
        config = self.config.with_context(lang="ar_001")
        self.assertEqual(config._nuqtapass_adjusted("stamp_undo", None, {"stamps": 3, "stampsRequired": 6}),
                         "انشال ختم · الأختام الحين: 3 من 6")
        self.assertEqual(config._nuqtapass_adjusted("points", 50, {"delta": 50, "points": 1454}),
                         "تعدّلت النقاط: \u2066+50\u2069 · الرصيد الحين: 1,454")
