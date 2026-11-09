from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from odoo.addons.nuqtapass_loyalty.lib import phone as phone_lib
from odoo.addons.nuqtapass_loyalty.lib.phone import normalise_e164

# (what was typed, company country, its calling code, what is sent). Checked with Odoo's optional `phonenumbers`
# library and again with the built-in length table, so both ways agree.
CASES = [
    # Oman: 8-digit mobiles.
    ("9123 4567", "OM", 968, "+96891234567"),
    ("94176872", "OM", 968, "+96894176872"),
    ("+96894176872", "OM", 968, "+96894176872"),
    ("+968 9123-4567", "OM", 968, "+96891234567"),
    ("0096891234567", "OM", 968, "+96891234567"),
    ("96891234567", "OM", 968, "+96891234567"),
    # The live bug: "9417872" (a digit missing) became "+9689417872" and NuqtaPass made a wrong customer.
    ("9417872", "OM", 968, None),
    ("+9689417872", "OM", 968, None),
    ("941768721", "OM", 968, None),
    # UAE: 9 digits after the code.
    ("050 123 4567", "AE", 971, "+971501234567"),
    ("+971 50 123 4567", "OM", 968, "+971501234567"),
    ("+971 50 123 456", "OM", 968, None),
    # KSA, Kuwait, Qatar, Bahrain, Jordan.
    ("0551234567", "SA", 966, "+966551234567"),
    ("5123 4567", "KW", 965, "+96551234567"),
    ("3312 3456", "QA", 974, "+97433123456"),
    ("3612 3456", "BH", 973, "+97336123456"),
    ("079 123 4567", "JO", 962, "+962791234567"),
    ("+962 79 123 456", "OM", 968, None),
    # Elsewhere: the trunk zero goes.
    ("07400 123456", "GB", 44, "+447400123456"),
    # Garbage.
    (None, "OM", 968, None),
    ("", "OM", 968, None),
    ("   ", "OM", 968, None),
    ("abc", "OM", 968, None),
    ("+", "OM", 968, None),
    ("hello 12", "OM", 968, None),
    ("123", "OM", 968, None),
    ("+1234567890123456", "OM", 968, None),
    # No company country: only "+..." numbers can be read.
    ("91234567", None, None, None),
    ("+96891234567", None, None, "+96891234567"),
]


def _check(case):
    for raw, region, code, expected in CASES:
        with case.subTest(raw=raw, region=region):
            case.assertEqual(normalise_e164(raw, region, code), expected)


@tagged("post_install", "-at_install", "nuqtapass")
class TestPhone(TransactionCase):
    def test_cases(self):
        _check(self)

    def test_uses_phonenumbers_when_odoo_has_it(self):
        self.assertIsNotNone(phone_lib.phonenumbers, "odoo:20.0 ships phonenumbers")

    def test_landline_is_not_a_mobile(self):
        self.assertIsNone(normalise_e164("2412 3456", "OM", 968))


@tagged("post_install", "-at_install", "nuqtapass")
class TestPhoneWithoutLibrary(TransactionCase):
    """An Odoo without `phonenumbers` (it is optional): the GCC + Jordan length table still catches short numbers."""

    def test_cases(self):
        with patch.object(phone_lib, "phonenumbers", None):
            _check(self)
