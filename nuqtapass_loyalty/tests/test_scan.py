from odoo.tests import TransactionCase, tagged

from odoo.addons.nuqtapass_loyalty.lib.scan import classify

CARD = "cccccccc-1111-4111-8111-111111111111"


@tagged("post_install", "-at_install", "nuqtapass")
class TestScan(TransactionCase):
    """What a till scan or a typed value is: a Wallet card id (new passes), a phone (older passes, typing) or neither."""

    def test_card_id_any_case_and_spaces(self):
        self.assertEqual(classify(f"  {CARD.upper()} "), ("card", CARD))

    def test_phone_shapes(self):
        for text in ("+96894176872", "94176872", "96894176872", "00968 9417 6872", "9417-6872"):
            with self.subTest(text=text):
                self.assertEqual(classify(text), ("phone", text.strip()))

    def test_other_codes_are_neither(self):
        for text in ("", None, "COFFEE-01", "1234567", "1234567890123456", "cccccccc-1111", f"{CARD}x", "+"):
            with self.subTest(text=text):
                self.assertEqual(classify(text), (None, None))
