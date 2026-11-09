from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from odoo.addons.nuqtapass_loyalty.lib.client import ApiResult, NuqtaPassClient

STAMP_CARD = "cccccccc-1111-4111-8111-111111111111"
PHONE = "+96891234567"


def refused(error, code=None, status=400):
    return ApiResult(False, status, None, error, code, False)


@tagged("post_install", "-at_install", "nuqtapass")
class TestPosRefusals(TransactionCase):
    """NuqtaPass's refusals on the till, by code (models/pos_refusal.py). English here; Arabic in test_pos_i18n."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.country_id = cls.env.ref("base.om")
        icp = cls.env["ir.config_parameter"].sudo()
        icp.set_param("nuqtapass_loyalty.till_enabled", "True")
        icp.set_param("nuqtapass_loyalty.api_key", "sip_test")
        cls.config = cls.env["pos.config"].create({"name": "Till refusals"}).with_context(lang="en_US")

    def _line(self, result):
        return self.config._nuqtapass_refusal(result)

    def test_every_listed_code_has_its_own_words(self):
        codes = ("CARD_FULL", "CARD_INACTIVE", "CARD_NOT_FOUND", "OTHER_SHOP", "CARD_MISMATCH", "VOUCHER_MISMATCH",
                 "WRONG_CARD_TYPE", "POINTS_TOO_SMALL", "VOUCHER_SAME_PHONE", "REF_CONFLICT", "IN_PROGRESS",
                 "ORDER_REFUNDED", "NOT_ADJUSTABLE", "MISSING_REASON", "INVALID_REASON", "PLAN_UPGRADE_REQUIRED",
                 "PLAN_ENDED", "SUBSCRIPTION_EXPIRED", "SHOP_PAUSED", "RATE_LIMITED")
        for code in codes:
            with self.subTest(code=code):
                text, detail = self._line(refused("Server words", code))
                self.assertNotEqual(text, "Server words")
                self.assertIsNone(detail)

    def test_known_code_words(self):
        self.assertEqual(self._line(refused("Card is full or no longer active", "CARD_FULL")),
                         ("This card is full. Give the reward first, then add stamps again.", None))
        self.assertEqual(self._line(refused("Voucher already used on this iPhone", "VOUCHER_SAME_PHONE"))[0],
                         "This iPhone already used this offer.")
        self.assertEqual(self._line(refused("Reason is required", "MISSING_REASON"))[0],
                         "Write why, in 3 to 200 characters.")

    def test_any_invalid_code_is_one_line(self):
        for code in ("INVALID_CARD_ID", "INVALID_POINTS", "INVALID_SOMETHING_NEW"):
            with self.subTest(code=code):
                self.assertEqual(self._line(refused("Bad " + code, code)),
                                 ("Something is missing. Look the customer up again.", None))

    def test_refusals_without_a_code_keep_nuqtapass_words_in_english(self):
        for words in ("Not enough points, or the card has expired. Balance: 40",
                      "Per-visit limit is 5.000 OMR (100 points). Ask an admin to override, or reduce the amount.",
                      "Not enough credit. Balance is 2.000 OMR.", "Only 2 left on this pack", "No stamps to undo"):
            with self.subTest(words=words):
                self.assertEqual(self._line(refused(words)), (words, None))

    def test_unknown_code_shows_nuqtapass_words_in_english(self):
        self.assertEqual(self._line(refused("Something brand new", "NEW_CODE")), ("Something brand new", None))
        self.assertEqual(self._line(refused("", "NEW_CODE")), ("We couldn't finish this. Try again.", None))

    def test_redeem_window_and_correction_use_them(self):
        with patch.object(NuqtaPassClient, "redeem", return_value=refused("Card mismatch", "CARD_MISMATCH", 409)):
            res = self.config._nuqtapass_redeem(PHONE, STAMP_CARD, "reward")
        self.assertEqual((res["error"], res["message"]),
                         ("refused", "This card changed at NuqtaPass. Look the customer up again."))
        self.assertNotIn("detail", res)
        with patch.object(NuqtaPassClient, "customer", return_value=refused("Slow down", "RATE_LIMITED", 429)):
            res = self.config._nuqtapass_lookup(PHONE)
        self.assertEqual(res["message"], "Too many tries. Wait a minute and try again.")

    def test_expired_access_is_not_called_a_bad_key(self):
        res = self.config._nuqtapass_failure(refused("Subscription expired", "SUBSCRIPTION_EXPIRED", 403))
        self.assertEqual(res["message"], "The shop's NuqtaPass access has ended. The owner can renew it on nuqtapass.com.")
        res = self.config._nuqtapass_failure(refused("Invalid key", "UNAUTHORIZED", 401))
        self.assertEqual(res["message"], "NuqtaPass refused the key. Check it in Settings.")
