from types import SimpleNamespace
from unittest.mock import patch

from odoo.exceptions import AccessError
from odoo.tests import tagged

from odoo.addons.nuqtapass_loyalty.lib.client import ApiResult, NuqtaPassClient
from odoo.addons.nuqtapass_loyalty_pos.controllers.main import NuqtaPassPosController

from .common import (DOWN, PACK_CARD, PHONE, POINTS_CARD, PREPAID_CARD, STAMP_CARD, VOUCHER, VOUCHER_CARD,
                     NuqtaPassUsesCommon, ok, refused)

REF = "261-1-000042"
POINTS_USE = {"use": "points", "card_id": POINTS_CARD, "points": 167, "label": "NuqtaPass points"}
CREDIT_USE = {"use": "credit", "card_id": PREPAID_CARD, "amount": 2.5, "label": "NuqtaPass credit"}
PACK_USE = {"use": "pack", "card_id": PACK_CARD, "uses": 1, "label": "Service pack (1 use)"}
REWARD_USE = {"use": "reward", "card_id": STAMP_CARD, "label": "Reward: free Coffee"}
VOUCHER_USE = {"use": "voucher", "card_id": VOUCHER_CARD, "voucher_id": VOUCHER, "label": "Reward: free Cake"}


def answer(use, duplicate=False, **extra):
    return ok({"transactionId": "t-" + use, "orderRef": REF, "use": use, "duplicate": duplicate, **extra})


@tagged("post_install", "-at_install", "nuqtapass")
class TestPosSpend(NuqtaPassUsesCommon):
    # ── what the module creates ───────────────────────────────────────
    def test_reward_product_is_a_hidden_service_without_tax(self):
        product = self.reward
        self.assertEqual(product, self.env["pos.config"]._nuqtapass_reward_product())  # one product, made once
        self.assertEqual(product.type, "service")
        self.assertFalse(product.taxes_id)
        self.assertTrue(product.available_in_pos)
        self.assertIn(product, self.config._get_special_products())  # loaded by the till, not listed

    def test_credit_method_is_a_bank_method_on_its_own_journal(self):
        method = self.credit_pm
        self.assertTrue(method.nuqtapass_credit)
        self.assertEqual(method.type, "bank")
        self.assertEqual(method.journal_id.type, "bank")
        self.assertEqual(method.journal_id.code, "NPCR")
        # A use settles the shop's prepaid-credit liability, as a gift card does.
        self.assertEqual(method.outstanding_account_id.account_type, "liability_current")
        self.assertIn(method, self.config.payment_method_ids)
        self.assertEqual(self.env["pos.payment.method"]._nuqtapass_credit_method(self.env.company), method)

    def test_reward_product_is_made_when_missing(self):
        # Not XML data: an upgrade loads this module before `sale`, whose required product fields then stay empty.
        # It is made at run time, once, with the whole registry loaded.
        self.env["ir.model.data"].search([("module", "=", "nuqtapass_loyalty_pos"),
                                          ("name", "=", "product_nuqtapass_reward")]).unlink()
        product = self.env["pos.config"]._nuqtapass_reward_product()
        self.assertTrue(product)
        self.assertNotEqual(product, self.reward)
        self.assertEqual(self.env.ref("nuqtapass_loyalty_pos.product_nuqtapass_reward"), product)
        self.assertEqual((product.type, product.taxes_id.ids, product.available_in_pos), ("service", [], True))
        self.assertEqual(self.env["pos.config"]._nuqtapass_reward_product(), product)

    def test_opening_a_till_adds_the_credit_method(self):
        config = self.env["pos.config"].create({"name": "Third till"})
        config.payment_method_ids -= self.credit_pm
        config.open_ui()
        self.assertIn(self.credit_pm, config.payment_method_ids)

    def test_new_till_gets_the_credit_method(self):
        config = self.env["pos.config"].create({"name": "Second till"})
        self.assertIn(self.credit_pm, config.payment_method_ids)

    def test_order_line_fields_go_to_and_from_the_till(self):
        fields = self.env["pos.order.line"]._load_pos_data_fields(self.config)
        for name in ("nuqtapass_use", "nuqtapass_card_id", "nuqtapass_voucher_id", "nuqtapass_qty"):
            self.assertIn(name, fields)
        order = self._sync([self._line(self.coffee, 2, 2.5), self._points_line(50, 1.5)], [(self.cash_pm1, 3.5)])
        line = order.lines.filtered("nuqtapass_use")
        self.assertEqual((line.nuqtapass_use, line.nuqtapass_card_id, line.nuqtapass_qty), ("points", POINTS_CARD, 50))

    def test_credit_paid_order_books_on_the_liability_at_close(self):
        self._sync([self._line(self.coffee, 2, 2.5)], [(self.credit_pm, 2.0), (self.cash_pm1, 3.0)])
        self.pos_session.close_session_from_ui({self.cash_pm1.id: 3.0})
        self.assertEqual(self.pos_session.state, "closed")
        lines = self.env["account.move.line"].search([("account_id", "=", self.credit_pm.outstanding_account_id.id)])
        self.assertAlmostEqual(sum(lines.mapped("debit")) - sum(lines.mapped("credit")), 2.0)

    # ── Validate: one /redeem per use, with the order's reference ────
    def _spend(self, uses, results):
        with patch.object(NuqtaPassClient, "redeem", side_effect=results) as mocked:
            res = self.config._nuqtapass_spend(REF, PHONE, uses)
        return res, mocked

    def test_each_kind_is_sent_with_the_order_reference(self):
        self.config.nuqtapass_branch = "Qurum"
        res, mocked = self._spend(
            [POINTS_USE, CREDIT_USE, PACK_USE, REWARD_USE, VOUCHER_USE],
            [answer("points", pointsUsed=167), answer("credit"), answer("pack"), answer("reward"), answer("voucher")])
        self.assertTrue(res["ok"], res)
        base = {"phone": PHONE, "orderRef": REF, "branch": "Qurum"}
        self.assertEqual([c.args[0] for c in mocked.call_args_list], [
            dict(base, cardId=POINTS_CARD, action="reward", points=167),
            dict(base, cardId=PREPAID_CARD, action="credit", amount=2.5),
            dict(base, cardId=PACK_CARD, action="pack", uses=1),
            dict(base, cardId=STAMP_CARD, action="reward"),
            dict(base, cardId=VOUCHER_CARD, action="voucher", voucherId=VOUCHER),
        ])
        used = self.Use.search([("order_ref", "=", REF)])
        self.assertEqual(sorted(used.mapped("use")), ["credit", "pack", "points", "reward", "voucher"])
        self.assertEqual(used.filtered(lambda u: u.use == "points").quantity, 167)
        self.assertEqual(used.filtered(lambda u: u.use == "credit").amount, 2.5)

    def test_a_second_validate_resends_and_records_once(self):
        self._spend([POINTS_USE], [answer("points")])
        res, mocked = self._spend([POINTS_USE], [answer("points", duplicate=True)])
        self.assertTrue(res["ok"])
        mocked.assert_called_once()  # NuqtaPass answers the first answer and spends nothing more
        self.assertEqual(self.Use.search_count([("order_ref", "=", REF)]), 1)

    def test_refused_use_stops_and_names_the_line(self):
        res, mocked = self._spend(
            [CREDIT_USE, POINTS_USE],
            [answer("credit"), refused("Not enough points (1200 left)", "POINTS_TOO_SMALL")])
        self.assertEqual(mocked.call_count, 2)
        self.assertEqual((res["ok"], res["error"], res["index"]), (False, "refused", 1))
        self.assertEqual(res["message"], "NuqtaPass points: Not enough points (1200 left). "
                                         "Remove this line to take payment without it.")
        # What was already used stays recorded; a new Validate resends it (NuqtaPass answers it as a duplicate).
        self.assertEqual(self.Use.search([("order_ref", "=", REF)]).mapped("use"), ["credit"])

    def test_unreachable_stops_payment(self):
        res, _mocked = self._spend([POINTS_USE], [DOWN])
        self.assertEqual((res["ok"], res["error"]), (False, "unreachable"))
        self.assertEqual(res["message"], "NuqtaPass can't be reached: remove the NuqtaPass lines to take payment "
                                         "without them.")
        server_error = ApiResult(False, 502, None, "Bad gateway", None, True)
        self.assertEqual(self._spend([POINTS_USE], [server_error])[0]["error"], "unreachable")

    def test_in_progress_asks_to_press_validate_again(self):
        busy = ApiResult(False, 409, None, "This use is being recorded", "IN_PROGRESS", True)
        res, _mocked = self._spend([POINTS_USE], [busy])
        self.assertEqual((res["ok"], res["error"]), (False, "busy"))
        self.assertIn("Validate again", res["message"])

    def test_changed_amount_says_what_was_used(self):
        self._spend([POINTS_USE], [answer("points")])
        conflict = ApiResult(False, 409, None, "This order already used points with another amount", "REF_CONFLICT",
                             False)
        res, _mocked = self._spend([dict(POINTS_USE, points=100)], [conflict])
        self.assertEqual((res["ok"], res["error"], res["index"]), (False, "refused", 0))
        self.assertEqual(res["message"], "NuqtaPass points: this order already used 167 at NuqtaPass. "
                                         "Set the line back to that, or remove it.")

    def test_bad_input_never_calls_nuqtapass(self):
        for uses in ([dict(POINTS_USE, points=0)], [dict(POINTS_USE, points=1.5)], [dict(CREDIT_USE, amount=-1)],
                     [dict(PACK_USE, uses=11)], [dict(POINTS_USE, use="cash")], [dict(POINTS_USE, card_id="")],
                     [POINTS_USE] * 21, "x", [POINTS_USE, POINTS_USE]):
            with self.subTest(uses=uses):
                res, mocked = self._spend(uses, [])
                mocked.assert_not_called()
                self.assertEqual(res["error"], "bad_request")
        with patch.object(NuqtaPassClient, "redeem") as mocked:
            self.assertEqual(self.config._nuqtapass_spend("", PHONE, [POINTS_USE])["error"], "bad_request")
            self.assertEqual(self.config._nuqtapass_spend("x" * 121, PHONE, [POINTS_USE])["error"], "bad_request")
            self.assertEqual(self.config._nuqtapass_spend(REF, "12", [POINTS_USE])["error"], "invalid_phone")
        mocked.assert_not_called()

    def test_nothing_to_spend_is_ok(self):
        res, mocked = self._spend([], [])
        self.assertEqual(res, {"ok": True, "used": []})
        mocked.assert_not_called()

    def test_order_shows_what_it_used(self):
        self._spend([POINTS_USE, CREDIT_USE], [answer("points"), answer("credit")])
        order = self._sync([self._line(self.coffee, 4, 2.5), self._points_line(167, 5.01)],
                           [(self.credit_pm, 2.5), (self.cash_pm1, 2.49)], ref=REF)
        self.assertEqual(order.nuqtapass_used, "Points used: 167 · Credit used: 2.5")

    def test_only_point_of_sale_users_may_spend(self):
        user = self.env["res.users"].create({"name": "No POS", "login": "nopos", "group_ids": []})
        controller = NuqtaPassPosController()
        fake = SimpleNamespace(env=self.env(user=user))
        with patch("odoo.addons.nuqtapass_loyalty_pos.controllers.main.request", new=fake):
            with self.assertRaises(AccessError):
                controller.spend(self.config.id, REF, PHONE, [POINTS_USE])
