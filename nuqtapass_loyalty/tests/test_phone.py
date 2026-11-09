from odoo.tests import TransactionCase, tagged

from odoo.addons.nuqtapass_loyalty.lib.phone import normalise_e164


@tagged("post_install", "-at_install", "nuqtapass")
class TestPhone(TransactionCase):
    def test_local_oman_number_gets_country_code(self):
        self.assertEqual(normalise_e164("9123 4567", 968), "+96891234567")

    def test_plus_number_kept(self):
        self.assertEqual(normalise_e164("+968 9123-4567", 968), "+96891234567")

    def test_double_zero_prefix(self):
        self.assertEqual(normalise_e164("0096891234567", 968), "+96891234567")

    def test_country_code_without_plus(self):
        self.assertEqual(normalise_e164("96891234567", 968), "+96891234567")

    def test_trunk_zero_dropped(self):
        self.assertEqual(normalise_e164("07700 900123", 44), "+447700900123")

    def test_other_gulf_number_with_plus(self):
        self.assertEqual(normalise_e164("+971 50 123 4567", 968), "+971501234567")

    def test_empty_and_garbage(self):
        for raw in (None, "", "   ", "abc", "+"):
            self.assertIsNone(normalise_e164(raw, 968), raw)

    def test_too_short_or_long(self):
        self.assertIsNone(normalise_e164("123", 968))
        self.assertIsNone(normalise_e164("+1234567890123456", 968))

    def test_no_country_and_no_plus(self):
        self.assertIsNone(normalise_e164("91234567", None))
        self.assertEqual(normalise_e164("+96891234567", None), "+96891234567")
