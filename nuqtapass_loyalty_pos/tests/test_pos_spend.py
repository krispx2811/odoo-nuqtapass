import time
from types import SimpleNamespace
from unittest.mock import patch

from odoo.exceptions import AccessError, UserError
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

    def test_till_data_makes_the_missing_reward_product(self):
        # A till already open (not opened again from the back office) still gets the product when it loads: without
        # it the payment panel shows no actions and "Use points" adds nothing.
        self.env["ir.model.data"].search([("module", "=", "nuqtapass_loyalty_pos"),
                                          ("name", "=", "product_nuqtapass_reward")]).unlink()
        self.config.invalidate_recordset()
        product = self.config.nuqtapass_reward_product_id
        self.assertTrue(product)
        self.assertEqual(self.env.ref("nuqtapass_loyalty_pos.product_nuqtapass_reward"), product)
        self.assertIn(product, self.config._get_special_products())

    def test_opening_a_till_adds_the_credit_method(self):
        config = self.env["pos.config"].create({"name": "Third till"})
        config.payment_method_ids -= self.credit_pm
        config.open_ui()
        self.assertIn(self.credit_pm, config.payment_method_ids)

    def _take_off_the_till(self, method):
        """As a till upgraded with its session open: the method isn't on it (Odoo refuses removing it then)."""
        field = self.config._fields["payment_method_ids"]
        self.env.cr.execute(f"DELETE FROM {field.relation} WHERE {field.column1} = %s AND {field.column2} = %s",
                            (self.config.id, method.id))
        self.config.invalidate_recordset(["payment_method_ids"])
        self.assertNotIn(method, self.config.payment_method_ids)

    def test_till_page_load_adds_the_credit_method_to_an_open_session(self):
        # Kareem's till: a session opened before the upgrade never runs open_ui again; reloading the till page must
        # still bring the method (on the till and in what the page loads).
        self._take_off_the_till(self.credit_pm)
        self.assertEqual(self.pos_session.state, "opened")
        # A reload may ask for some models only.
        data = self.pos_session.load_data(["pos.config", "pos.payment.method"])
        self.assertIn(self.credit_pm, self.config.payment_method_ids)
        config = data["pos.config"][0]
        self.assertIn(self.credit_pm.id, config["payment_method_ids"])
        methods = {pm["id"]: pm for pm in data["pos.payment.method"]}
        self.assertTrue(methods[self.credit_pm.id]["nuqtapass_credit"])

    def test_upgrade_makes_the_missing_credit_method(self):
        # A database upgraded from a version without NuqtaPass credit (data/nuqtapass_credit.xml runs on every
        # upgrade): the method is made and put on the company's tills; a second run changes nothing.
        self._take_off_the_till(self.credit_pm)
        self.credit_pm.nuqtapass_credit = False
        self.env["pos.payment.method"]._nuqtapass_ensure_all()
        method = self.env["pos.payment.method"].search(
            [("nuqtapass_credit", "=", True), ("company_id", "=", self.env.company.id)])
        self.assertEqual(len(method), 1)
        self.assertIn(method, self.config.payment_method_ids)
        self.assertEqual(method.outstanding_account_id.account_type, "liability_current")
        self.env["pos.payment.method"]._nuqtapass_ensure_all()
        self.assertEqual(self.env["pos.payment.method"].search_count(
            [("nuqtapass_credit", "=", True), ("company_id", "=", self.env.company.id)]), 1)

    def test_credit_method_gets_its_arabic_name_with_a_session_open(self):
        # Kareem's till is open during the upgrade: Odoo refuses changing an open session's method, but the name's
        # Arabic still goes on (and nothing else the upgrade does is undone).
        self.env["res.lang"]._activate_lang("ar_001")
        self.assertEqual(self.pos_session.state, "opened")
        self.assertIn(self.credit_pm, self.pos_session.payment_method_ids)
        self.credit_pm.with_context(nuqtapass_name_only=True).update_field_translations(
            "name", {"ar_001": "NuqtaPass credit"})  # as before this version
        self.env["pos.payment.method"]._nuqtapass_ensure_all()
        self.assertEqual(self.credit_pm.with_context(lang="ar_001").name, "رصيد نقطة باس")
        self.assertEqual(self.credit_pm.with_context(lang="en_US").name, "NuqtaPass credit")
        # Other changes stay refused while the session is open.
        with self.assertRaises(UserError):
            self.credit_pm.name = "Something else"

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
        # The uses go out at the same time, in any order: each answer goes with its use's card.
        by_card = {str(use.get("card_id") or "").lower(): result for use, result in zip(uses, results)}
        with patch.object(NuqtaPassClient, "redeem", side_effect=lambda body: by_card[body["cardId"]]) as mocked:
            res = self.config._nuqtapass_spend(REF, PHONE, uses)
        return res, mocked

    def test_each_kind_is_sent_with_the_order_reference(self):
        self.config.nuqtapass_branch = "Qurum"
        res, mocked = self._spend(
            [POINTS_USE, CREDIT_USE, PACK_USE, REWARD_USE, VOUCHER_USE],
            [answer("points", pointsUsed=167), answer("credit"), answer("pack"), answer("reward"), answer("voucher")])
        self.assertTrue(res["ok"], res)
        base = {"phone": PHONE, "orderRef": REF, "branch": "Qurum"}
        self.assertCountEqual([c.args[0] for c in mocked.call_args_list], [
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
            [answer("credit"), refused("Not enough points, or the card has expired. Balance: 1200")])
        self.assertEqual(mocked.call_count, 2)
        self.assertEqual((res["ok"], res["error"], res["index"]), (False, "refused", 1))
        self.assertEqual(res["message"], "NuqtaPass points: Not enough points, or the card has expired. Balance: 1200. "
                                         "Remove this line to take payment without it.")
        # What was already used stays recorded; a new Validate resends it (NuqtaPass answers it as a duplicate).
        self.assertEqual(self.Use.search([("order_ref", "=", REF)]).mapped("use"), ["credit"])

    def test_uses_go_out_at_the_same_time(self):
        # Kareem's till: five uses one after another took ~21 s (one internet round trip each).
        def slow(body):
            time.sleep(0.4)
            return answer(body["action"])
        started = time.monotonic()
        with patch.object(NuqtaPassClient, "redeem", side_effect=slow) as mocked:
            res = self.config._nuqtapass_spend(REF, PHONE, [POINTS_USE, CREDIT_USE, PACK_USE, REWARD_USE, VOUCHER_USE])
        self.assertTrue(res["ok"], res)
        self.assertEqual(mocked.call_count, 5)
        self.assertLess(time.monotonic() - started, 1.2)  # about one call's time, not five
        self.assertEqual([u["index"] for u in res["used"]], [0, 1, 2, 3, 4])

    def test_a_refusal_keeps_the_other_spent_uses(self):
        # All went out together: the ones NuqtaPass spent after the refused one are recorded too.
        res, mocked = self._spend([POINTS_USE, CREDIT_USE, PACK_USE],
                                  [answer("points"), refused("Not enough credit"), answer("pack")])
        self.assertEqual(mocked.call_count, 3)
        self.assertEqual((res["ok"], res["error"], res["index"]), (False, "refused", 1))
        self.assertEqual(sorted(self.Use.search([("order_ref", "=", REF)]).mapped("use")), ["pack", "points"])
        # The first failing line is the one named, also when an earlier one is unreachable.
        res, _mocked = self._spend([CREDIT_USE, PACK_USE], [DOWN, refused("No uses left")])
        self.assertEqual((res["error"], res["index"]), ("unreachable", 0))

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
