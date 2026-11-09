from unittest.mock import patch

from odoo.tests import TransactionCase, new_test_user, tagged

from odoo.addons.nuqtapass_loyalty.lib.client import ApiResult, NuqtaPassClient
from odoo.addons.nuqtapass_loyalty_pos.controllers.main import NuqtaPassPosController

STAMP_CARD = "cccccccc-1111-4111-8111-111111111111"
POINTS_CARD = "aaaaaaaa-2222-4222-8222-222222222222"
MANAGER_GROUP = "point_of_sale.group_pos_manager"


def ok(data):
    return ApiResult(True, 200, data, None, None, False)


def refused(error, code=None, status=400):
    return ApiResult(False, status, None, error, code, False)


@tagged("post_install", "-at_install", "nuqtapass")
class TestPosAdjust(TransactionCase):
    """Corrections from the till (spec 2026-11-09 §3): only "Point of Sale / Administrator" users, with a reason."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.country_id = cls.env.ref("base.om")
        icp = cls.env["ir.config_parameter"].sudo()
        icp.set_param("nuqtapass_loyalty.till_enabled", "True")
        icp.set_param("nuqtapass_loyalty.api_key", "sip_test")
        cls.config = cls.env["pos.config"].create({"name": "Till"})
        cls.manager = new_test_user(cls.env, "np_manager", groups=MANAGER_GROUP, name="Mona Al Hinai")
        cls.cashier = new_test_user(cls.env, "np_cashier", groups="point_of_sale.group_pos_user", name="Saif")

    def _as(self, user):
        return self.config.with_user(user)

    def test_group_is_odoos_pos_administrator(self):
        self.assertEqual(self.env.ref(MANAGER_GROUP).name, "Administrator")
        self.assertTrue(self.manager.has_group(MANAGER_GROUP))
        self.assertFalse(self.cashier.has_group(MANAGER_GROUP))

    def test_lookup_says_who_may_correct(self):
        answer = ok({"phone": "+96891234567", "walletAdded": True, "cards": []})
        with patch.object(NuqtaPassClient, "customer", return_value=answer):
            self.assertTrue(self._as(self.manager)._nuqtapass_lookup("91234567")["canCorrect"])
            self.assertFalse(self._as(self.cashier)._nuqtapass_lookup("91234567")["canCorrect"])

    def test_a_cashier_is_refused_without_calling_nuqtapass(self):
        with patch.object(NuqtaPassClient, "adjust") as adjust:
            res = self._as(self.cashier)._nuqtapass_adjust(STAMP_CARD, "stamp_undo", None, "Pressed twice")
        adjust.assert_not_called()
        self.assertEqual(res["error"], "not_allowed")
        self.assertEqual(res["message"], "Only Point of Sale administrators can correct cards.")

    def test_bad_input_is_refused_without_calling_nuqtapass(self):
        cases = [
            (STAMP_CARD, "stamp_set", None, "Pressed twice", "bad_request"),
            (STAMP_CARD, "credit", None, "Pressed twice", "bad_request"),
            ("", "stamp_add", None, "Pressed twice", "bad_request"),
            ("x" * 65, "stamp_add", None, "Pressed twice", "bad_request"),
            (STAMP_CARD, "stamp_add", None, "  ab  ", "bad_reason"),
            (STAMP_CARD, "stamp_add", None, None, "bad_reason"),
            (STAMP_CARD, "stamp_add", None, "x" * 201, "bad_reason"),
            (POINTS_CARD, "points", 0, "Wrong amount", "bad_delta"),
            (POINTS_CARD, "points", None, "Wrong amount", "bad_delta"),
            (POINTS_CARD, "points", 1.5, "Wrong amount", "bad_delta"),
            (POINTS_CARD, "points", True, "Wrong amount", "bad_delta"),
            (POINTS_CARD, "points", "50", "Wrong amount", "bad_delta"),
            (POINTS_CARD, "points", 1_000_001, "Wrong amount", "bad_delta"),
            (POINTS_CARD, "points", -1_000_001, "Wrong amount", "bad_delta"),
        ]
        with patch.object(NuqtaPassClient, "adjust") as adjust:
            for card, action, delta, reason, error in cases:
                with self.subTest(action=action, delta=delta, reason=reason):
                    res = self._as(self.manager)._nuqtapass_adjust(card, action, delta, reason)
                    self.assertEqual(res["error"], error)
        adjust.assert_not_called()

    def test_stamp_undo_sends_the_reason_and_the_odoo_users_name(self):
        done = ok({"action": "stamp_undo", "cardId": STAMP_CARD, "type": "STAMPS", "stamps": 3, "stampsRequired": 6})
        with patch.object(NuqtaPassClient, "adjust", return_value=done) as adjust:
            res = self._as(self.manager)._nuqtapass_adjust(STAMP_CARD.upper(), "stamp_undo", 5, "  Pressed twice  ")
        adjust.assert_called_once_with({"cardId": STAMP_CARD, "action": "stamp_undo", "reason": "Pressed twice",
                                        "staffName": "Mona Al Hinai"})
        self.assertEqual(res, {"ok": True, "message": "Stamp taken off: 3 of 6 now."})

    def test_stamp_add(self):
        done = ok({"action": "stamp_add", "cardId": STAMP_CARD, "type": "STAMPS", "stamps": 5, "stampsRequired": 6})
        with patch.object(NuqtaPassClient, "adjust", return_value=done):
            res = self._as(self.manager)._nuqtapass_adjust(STAMP_CARD, "stamp_add", None, "Missed one")
        self.assertEqual(res, {"ok": True, "message": "Stamp added: 5 of 6 now."})

    def test_points_send_the_delta(self):
        done = ok({"action": "points", "cardId": POINTS_CARD, "type": "POINTS", "delta": 50, "points": 1454,
                   "totalPointsEarned": 2000})
        with patch.object(NuqtaPassClient, "adjust", return_value=done) as adjust:
            res = self._as(self.manager)._nuqtapass_adjust(POINTS_CARD, "points", 50, "Missed sale")
        self.assertEqual(adjust.call_args.args[0]["delta"], 50)
        self.assertEqual(res, {"ok": True, "message": "Points corrected: \u2066+50\u2069 · 1,454 now."})

    def test_points_take_off_and_the_cap_at_zero(self):
        taken = ok({"action": "points", "type": "POINTS", "delta": -40, "points": 1364, "totalPointsEarned": 2000})
        capped = ok({"action": "points", "type": "POINTS", "delta": -12, "points": 0, "totalPointsEarned": 2000})
        none = ok({"action": "points", "type": "POINTS", "delta": 0, "points": 0, "totalPointsEarned": 2000})
        manager = self._as(self.manager)
        with patch.object(NuqtaPassClient, "adjust", return_value=taken):
            self.assertEqual(manager._nuqtapass_adjust(POINTS_CARD, "points", -40, "Wrong sale")["message"],
                             "Points corrected: \u2066-40\u2069 · 1,364 now.")
        with patch.object(NuqtaPassClient, "adjust", return_value=capped):
            self.assertEqual(manager._nuqtapass_adjust(POINTS_CARD, "points", -50, "Wrong sale")["message"],
                             "Points corrected: \u2066-12\u2069 (all the card had) · 0 now.")
        with patch.object(NuqtaPassClient, "adjust", return_value=none):
            self.assertEqual(manager._nuqtapass_adjust(POINTS_CARD, "points", -50, "Wrong sale")["message"],
                             "The card has no points to take off.")

    def test_refusals_show_nuqtapass_words(self):
        manager = self._as(self.manager)
        for result in (refused("Card is full", "CARD_FULL"), refused("No stamps to undo"),
                       refused("Prepaid credit and pack uses can't be corrected: use a sale or a refund",
                               "NOT_ADJUSTABLE")):
            with self.subTest(code=result.code), patch.object(NuqtaPassClient, "adjust", return_value=result):
                res = manager._nuqtapass_adjust(STAMP_CARD, "stamp_add", None, "Missed one")
                self.assertEqual((res["ok"], res["error"], res["message"]), (False, "refused", result.error))
        with patch.object(NuqtaPassClient, "adjust", return_value=refused("Card not found", "CARD_NOT_FOUND", 404)):
            res = manager._nuqtapass_adjust(STAMP_CARD, "stamp_add", None, "Missed one")
        self.assertEqual(res["error"], "card_not_found")
        down = ApiResult(False, None, None, "Could not reach NuqtaPass", "NETWORK", True)
        with patch.object(NuqtaPassClient, "adjust", return_value=down):
            res = manager._nuqtapass_adjust(STAMP_CARD, "stamp_add", None, "Missed one")
        self.assertEqual(res["error"], "unreachable")

    def test_till_switched_off(self):
        self.env["ir.config_parameter"].sudo().set_param("nuqtapass_loyalty.till_enabled", "False")
        with patch.object(NuqtaPassClient, "adjust") as adjust:
            res = self._as(self.manager)._nuqtapass_adjust(STAMP_CARD, "stamp_add", None, "Missed one")
        adjust.assert_not_called()
        self.assertEqual(res["error"], "disabled")

    def test_route_is_there(self):
        route = NuqtaPassPosController.adjust.original_routing
        self.assertEqual(route["routes"], ["/nuqtapass_loyalty/pos/adjust"])
        self.assertEqual(route["auth"], "user")
