from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import tagged

from odoo.addons.nuqtapass_loyalty.lib.client import ApiResult, NuqtaPassClient
from odoo.addons.point_of_sale.tests.common import TestPoSCommon

CARD_URL = "https://nuqtapass.com/join/qahwa"
WHATSAPP = "https://api.whatsapp.com/send?phone=96891234567&text=Welcome"
SMS = "sms:+96891234567?body=Welcome"
QUIET = {"ok": True, "show_qr": False}
STAMP_CARD = "cccccccc-1111-4111-8111-111111111111"
POINTS_CARD = "aaaaaaaa-2222-4222-8222-222222222222"
VOUCHER_CARD = "dddddddd-1111-4111-8111-111111111111"
VOUCHER = "eeeeeeee-1111-4111-8111-111111111111"
STAMPS = {"cardId": STAMP_CARD, "type": "STAMPS", "stamps": 3, "stampsRequired": 6, "rewardReady": False,
          "points": 0, "pointsValue": 0, "balance": 0, "packUses": 0, "voucher": None}


def ok(data, status=200):
    return ApiResult(True, status, data, None, None, False)


@tagged("post_install", "-at_install", "nuqtapass")
class TestPosTill(TestPoSCommon):
    def setUp(self):
        super().setUp()
        self.config = self.basic_config
        self.env.company.country_id = self.env.ref("base.om")
        # Odoo 20: typed config parameters (get_param / set_param are gone).
        icp = self.env["ir.config_parameter"].sudo()
        icp.set_bool("nuqtapass_loyalty.till_enabled", True)
        icp.set_str("nuqtapass_loyalty.api_key", "sip_test")
        self.product = self.create_product("Coffee", self.categ_basic, 2.5, 1.0)
        self.customer.phone = "9123 4567"
        self.open_new_session()

    def _paid_order(self, customer=True):
        data = self.create_ui_order_data([(self.product, 1)], {}, customer=self.customer if customer else None)
        res = self.env["pos.order"].sync_from_ui([data])
        return self.env["pos.order"].browse(res["pos.order"][0]["id"])

    # ── look-up ───────────────────────────────────────────────────────
    def test_lookup_cleans_answer(self):
        answer = ok({"phone": "+96891234567", "walletAdded": True, "cardUrl": None, "welcome": None,
                     "cards": [dict(STAMPS, deviceKeyHash="secret")]})
        with patch.object(NuqtaPassClient, "customer", return_value=answer) as mocked:
            res = self.config._nuqtapass_lookup("9123 4567")
        mocked.assert_called_once_with("+96891234567")
        self.assertTrue(res["ok"])
        self.assertEqual(res["phone"], "+96891234567")
        self.assertEqual(res["cards"], [dict(STAMPS, current=True, pointsPerUnit=None, usesLeft=0, unit=None)])
        self.assertTrue(res["walletAdded"])
        self.assertIsNone(res["welcome"])

    def test_lookup_keeps_the_tier(self):
        tier = {"name": "GOLD", "cashbackPct": 10, "next": None, "color": "rgb(212, 175, 55)"}
        points = {"cardId": POINTS_CARD, "type": "POINTS", "points": 1404, "current": True, "tier": tier}
        with patch.object(NuqtaPassClient, "customer", return_value=ok({"walletAdded": True, "cards": [points]})):
            res = self.config._nuqtapass_lookup("91234567")
        self.assertEqual(res["cards"][0]["tier"], tier)

    def test_lookup_answers_nuqtapass_currency_not_the_till_currency(self):
        # Kareem, 2026-11-09: a till set up in US dollars still shows an Omani shop's NuqtaPass amounts in OMR.
        self.assertNotEqual(self.config.currency_id.name, "OMR")
        points = {"cardId": POINTS_CARD, "type": "POINTS", "points": 1404, "pointsValue": 42.12,
                  "pointsPerUnit": 33.333333, "current": True}
        answer = ok({"phone": "+96891234567", "walletAdded": True, "cards": [points],
                     "currency": {"code": "OMR", "symbol": "OMR", "decimals": 3},
                     "limits": {"pointsPerVisit": {"value": 10, "points": 333}}})
        with patch.object(NuqtaPassClient, "customer", return_value=answer):
            res = self.config._nuqtapass_lookup("91234567")
        self.assertEqual(res["currency"], {"code": "OMR", "symbol": "OMR", "decimals": 3})
        self.assertEqual(res["limits"], {"pointsPerVisit": {"value": 10, "points": 333}})
        self.assertEqual((res["cards"][0]["pointsValue"], res["cards"][0]["pointsPerUnit"]), (42.12, 33.333333))

    # ── look-up by the Wallet card's QR (its card id) ─────────────────
    def test_lookup_by_card_uses_the_card_and_answers_its_phone(self):
        answer = ok({"phone": "+96894176872", "walletAdded": True, "cards": [dict(STAMPS, current=True)]})
        with patch.object(NuqtaPassClient, "customer_by_card", return_value=answer) as by_card, \
                patch.object(NuqtaPassClient, "customer") as by_phone:
            res = self.config._nuqtapass_lookup(STAMP_CARD.upper())
        by_card.assert_called_once_with(STAMP_CARD)
        by_phone.assert_not_called()
        self.assertEqual((res["ok"], res["phone"]), (True, "+96894176872"))
        self.assertEqual([c["cardId"] for c in res["cards"]], [STAMP_CARD])

    def test_lookup_by_card_unknown_other_shop_or_malformed(self):
        for answer in (ApiResult(False, 404, None, "Card not found", "CARD_NOT_FOUND", False),
                       ApiResult(False, 400, None, "Invalid card id", "INVALID_CARD", False)):
            with self.subTest(code=answer.code), patch.object(NuqtaPassClient, "customer_by_card", return_value=answer):
                self.assertEqual(self.config._nuqtapass_lookup(STAMP_CARD),
                                 {"ok": False, "error": "card_not_found", "message": "This card isn't from this shop."})

    def test_lookup_by_card_without_a_usable_phone_is_refused(self):
        with patch.object(NuqtaPassClient, "customer_by_card", return_value=ok({"phone": "12", "cards": [STAMPS]})):
            self.assertEqual(self.config._nuqtapass_lookup(STAMP_CARD)["error"], "card_not_found")

    def test_lookup_by_card_when_till_off_or_no_key(self):
        self.env["ir.config_parameter"].sudo().set_str("nuqtapass_loyalty.api_key", False)
        self.assertEqual(self.config._nuqtapass_lookup(STAMP_CARD)["error"], "not_configured")
        self.env["ir.config_parameter"].sudo().set_bool("nuqtapass_loyalty.till_enabled", False)
        self.assertEqual(self.config._nuqtapass_lookup(STAMP_CARD)["error"], "disabled")

    def test_lookup_shows_only_current_cards(self):
        old_points = {"cardId": POINTS_CARD, "type": "POINTS", "points": 40, "current": False}
        answer = ok({"phone": "+96891234567", "walletAdded": True,
                     "cards": [old_points, dict(STAMPS, current=True)]})
        with patch.object(NuqtaPassClient, "customer", return_value=answer):
            res = self.config._nuqtapass_lookup("91234567")
        self.assertEqual([c["cardId"] for c in res["cards"]], [STAMP_CARD])

    def test_lookup_card_not_on_a_phone_carries_the_qr_links(self):
        answer = ok({"phone": "+96891234567", "walletAdded": False, "cardUrl": CARD_URL,
                     "welcome": {"cardUrl": CARD_URL, "whatsapp": WHATSAPP, "sms": SMS, "message": "Welcome"},
                     "cards": [STAMPS]})
        with patch.object(NuqtaPassClient, "customer", return_value=answer):
            res = self.config._nuqtapass_lookup("91234567")
        self.assertFalse(res["walletAdded"])
        self.assertEqual(res["welcome"], {"cardUrl": CARD_URL, "whatsapp": WHATSAPP, "sms": SMS})

    def test_lookup_bad_phone(self):
        self.assertEqual(self.config._nuqtapass_lookup("12")["error"], "invalid_phone")

    def test_lookup_offline(self):
        down = ApiResult(False, None, None, "Could not reach NuqtaPass", "NETWORK", True)
        with patch.object(NuqtaPassClient, "customer", return_value=down):
            self.assertEqual(self.config._nuqtapass_lookup("91234567")["error"], "unreachable")

    def test_lookup_without_key(self):
        self.env["ir.config_parameter"].sudo().set_str("nuqtapass_loyalty.api_key", False)
        self.assertEqual(self.config._nuqtapass_lookup("91234567")["error"], "not_configured")

    def test_lookup_when_till_off(self):
        self.env["ir.config_parameter"].sudo().set_bool("nuqtapass_loyalty.till_enabled", False)
        self.assertEqual(self.config._nuqtapass_lookup("91234567")["error"], "disabled")

    def test_lookup_no_card_here(self):
        missing = ApiResult(False, 404, None, "No card for this phone at this shop", "CARD_NOT_FOUND", False)
        with patch.object(NuqtaPassClient, "customer", return_value=missing):
            self.assertEqual(self.config._nuqtapass_lookup("91234567")["error"], "not_found")

    def test_lookup_plan_below_business(self):
        refused = ApiResult(False, 403, None, "Upgrade to Business to use the Odoo integration.",
                            "PLAN_UPGRADE_REQUIRED", True)
        with patch.object(NuqtaPassClient, "customer", return_value=refused):
            res = self.config._nuqtapass_lookup("91234567")
        self.assertEqual(res["error"], "refused")
        self.assertIn("Business", res["message"])

    # ── the button ────────────────────────────────────────────────────
    def test_redeem_stamp_reward_body(self):
        done = ok({"action": "reward", "type": "STAMPS", "cardId": STAMP_CARD, "stamps": 0, "timesRedeemed": 1})
        with patch.object(NuqtaPassClient, "redeem", return_value=done) as mocked:
            res = self.config._nuqtapass_redeem("91234567", STAMP_CARD, "reward")
        mocked.assert_called_once_with({"phone": "+96891234567", "cardId": STAMP_CARD, "action": "reward"})
        self.assertEqual(res, {"ok": True, "message": "Reward given."})

    def test_redeem_points_sends_how_many(self):
        done = ok({"action": "reward", "type": "POINTS", "cardId": POINTS_CARD, "pointsRedeemed": 50,
                   "value": 2.5, "remainingPoints": 10})
        with patch.object(NuqtaPassClient, "redeem", return_value=done) as mocked:
            res = self.config._nuqtapass_redeem("91234567", POINTS_CARD, "reward", points=50)
        mocked.assert_called_once_with({"phone": "+96891234567", "cardId": POINTS_CARD, "action": "reward", "points": 50})
        self.assertEqual(res, {"ok": True, "message": "Points used."})

    def test_redeem_points_must_be_a_whole_number(self):
        for bad in (0, -5, 1.5, "50", True, 10_000_001):
            self.assertEqual(self.config._nuqtapass_redeem("91234567", POINTS_CARD, "reward", points=bad)["error"],
                             "bad_request", bad)
        # Points only go with a reward.
        self.assertEqual(self.config._nuqtapass_redeem("91234567", VOUCHER_CARD, "voucher", points=5)["error"],
                         "bad_request")

    def test_redeem_voucher_with_or_without_its_id(self):
        done = ok({"action": "voucher", "cardId": VOUCHER_CARD, "status": "REDEEMED", "timesRedeemed": 1})
        with patch.object(NuqtaPassClient, "redeem", return_value=done) as mocked:
            res = self.config._nuqtapass_redeem("91234567", VOUCHER_CARD, "voucher", VOUCHER)
            # A voucher from before the voucher list has no id (Part 1 PosCard voucher.id null).
            self.config._nuqtapass_redeem("91234567", VOUCHER_CARD, "voucher")
        self.assertEqual(mocked.call_args_list[0].args[0],
                         {"phone": "+96891234567", "cardId": VOUCHER_CARD, "action": "voucher", "voucherId": VOUCHER})
        self.assertEqual(mocked.call_args_list[1].args[0],
                         {"phone": "+96891234567", "cardId": VOUCHER_CARD, "action": "voucher"})
        self.assertEqual(res, {"ok": True, "message": "Voucher used."})

    def test_redeem_rejects_unknown_action_or_card(self):
        self.assertEqual(self.config._nuqtapass_redeem("91234567", STAMP_CARD, "delete")["error"], "bad_request")
        self.assertEqual(self.config._nuqtapass_redeem("91234567", "", "reward")["error"], "bad_request")

    def test_redeem_refusals_show_the_server_words(self):
        refused = ApiResult(False, 401, None, "Invalid key", "UNAUTHORIZED", True)
        with patch.object(NuqtaPassClient, "redeem", return_value=refused):
            self.assertEqual(self.config._nuqtapass_redeem("91234567", STAMP_CARD, "reward")["error"], "refused")
        wrong = ApiResult(False, 400, None, "Prepaid and pack cards are used on the NuqtaPass till, not with this button",
                          "WRONG_CARD_TYPE", False)
        with patch.object(NuqtaPassClient, "redeem", return_value=wrong):
            res = self.config._nuqtapass_redeem("91234567", STAMP_CARD, "reward")
        self.assertEqual(res["error"], "refused")
        self.assertEqual(res["message"], "This card is a different type, so it can't do that.")

    # ── after payment: the QR code for a card that isn't on a phone yet ─
    def test_after_payment_sends_now_and_shows_the_qr(self):
        order = self._paid_order()
        sold = ok({"kind": "SALE", "status": "OK", "duplicate": False,
                   "result": {"cardType": "STAMPS", "stamps": 1, "newCustomer": True}}, status=201)
        answer = ok({"walletAdded": False, "cardUrl": CARD_URL,
                     "welcome": {"cardUrl": CARD_URL, "whatsapp": WHATSAPP, "sms": SMS}, "cards": []})
        with patch.object(NuqtaPassClient, "sale", return_value=sold) as sale, \
                patch.object(NuqtaPassClient, "customer", return_value=answer) as customer:
            res = self.config._nuqtapass_after_payment(order.id)
        sale.assert_called_once()
        customer.assert_called_once_with("+96891234567")
        self.assertEqual(order.nuqtapass_sync_ids.state, "done")
        self.assertEqual(res, {"ok": True, "show_qr": True,
                               "welcome": {"cardUrl": CARD_URL, "whatsapp": WHATSAPP, "sms": SMS}})

    def test_after_payment_card_on_a_phone_shows_nothing(self):
        order = self._paid_order()
        with patch.object(NuqtaPassClient, "sale", return_value=ok({"status": "OK"}, status=201)), \
                patch.object(NuqtaPassClient, "customer", return_value=ok({"walletAdded": True, "cards": []})):
            self.assertEqual(self.config._nuqtapass_after_payment(order.id), QUIET)

    def test_after_payment_already_sent_is_not_sent_again(self):
        order = self._paid_order()
        order.nuqtapass_sync_ids.sudo().write({"state": "done", "next_attempt_at": False})
        answer = ok({"walletAdded": False, "cardUrl": CARD_URL, "cards": []})
        with patch.object(NuqtaPassClient, "sale") as sale, \
                patch.object(NuqtaPassClient, "customer", return_value=answer):
            res = self.config._nuqtapass_after_payment(order.id)
        sale.assert_not_called()
        self.assertTrue(res["show_qr"])

    def test_after_payment_send_failed_shows_nothing_and_cron_keeps_it(self):
        order = self._paid_order()
        down = ApiResult(False, None, None, "Could not reach NuqtaPass", "NETWORK", True)
        with patch.object(NuqtaPassClient, "sale", return_value=down), \
                patch.object(NuqtaPassClient, "customer") as customer:
            self.assertEqual(self.config._nuqtapass_after_payment(order.id), QUIET)
        customer.assert_not_called()
        self.assertEqual(order.nuqtapass_sync_ids.state, "pending")

    def test_after_payment_unknown_or_phoneless_order_shows_nothing(self):
        self.assertEqual(self.config._nuqtapass_after_payment(999999999), QUIET)
        self.assertEqual(self.config._nuqtapass_after_payment("junk"), QUIET)
        self.assertEqual(self.config._nuqtapass_after_payment(self._paid_order(customer=False).id), QUIET)

    def test_lookup_wrong_phone_never_calls_nuqtapass(self):
        with patch.object(NuqtaPassClient, "customer") as mocked:
            res = self.config._nuqtapass_lookup("9417872")
        mocked.assert_not_called()
        self.assertEqual(res, {"ok": False, "error": "invalid_phone", "message": "Phone number looks wrong: 9417872"})

    def test_after_payment_and_cron_send_the_row_once(self):
        order = self._paid_order()
        Sync = self.env["nuqtapass.sync"].sudo()
        sold = ok({"status": "OK", "duplicate": False, "result": {"stamps": 1}}, status=201)
        with patch.object(NuqtaPassClient, "sale", return_value=sold) as sale, \
                patch.object(NuqtaPassClient, "customer", return_value=ok({"walletAdded": True, "cards": []})):
            self.config._nuqtapass_after_payment(order.id)
            Sync._send_due(now=fields.Datetime.now() + timedelta(seconds=5))
            self.config._nuqtapass_after_payment(order.id)
        sale.assert_called_once()
        self.assertEqual(order.nuqtapass_sync_ids.state, "done")

    def test_after_payment_skips_a_row_the_cron_is_sending(self):
        order = self._paid_order()
        Sync = type(self.env["nuqtapass.sync"])
        with patch.object(Sync, "_claim", return_value=self.env["nuqtapass.sync"]), \
                patch.object(NuqtaPassClient, "sale") as sale, patch.object(NuqtaPassClient, "customer") as customer:
            self.assertEqual(self.config._nuqtapass_after_payment(order.id), QUIET)
        sale.assert_not_called()
        customer.assert_not_called()
        self.assertEqual((order.nuqtapass_sync_ids.state, order.nuqtapass_sync_ids.attempts), ("pending", 0))

    # ── the receipt screen: add the customer after paying, earn at once ─
    def _sold(self, card_type="POINTS", points=None, stamps=0):
        return ok({"status": "OK", "duplicate": False,
                   "result": {"cardType": card_type, "stamps": stamps,
                              "points": (3 if card_type == "POINTS" else 0) if points is None else points}}, status=201)

    def test_attach_phone_sends_now_and_answers_the_line(self):
        order = self._paid_order(customer=False)
        points = {"cardId": POINTS_CARD, "type": "POINTS", "points": 163, "pointsValue": 16.3, "current": True}
        with patch.object(NuqtaPassClient, "sale", return_value=self._sold()) as sale, \
                patch.object(NuqtaPassClient, "customer",
                             return_value=ok({"walletAdded": True, "cards": [STAMPS, points]})) as customer:
            res = self.config._nuqtapass_attach(order.id, "9123 4567")
        sale.assert_called_once()
        self.assertEqual(sale.call_args.args[0]["phone"], "+96891234567")
        self.assertEqual(sale.call_args.args[0]["orderRef"], order.pos_reference)
        customer.assert_called_once_with("+96891234567")
        self.assertEqual(order.nuqtapass_phone, "+96891234567")
        self.assertEqual(order.nuqtapass_sync_ids.state, "done")
        self.assertEqual(res["earned"], {"cardType": "POINTS", "stamps": 0, "points": 3})
        self.assertEqual((res["ok"], res["phone"], res["card"]["points"], res["show_qr"]),
                         (True, "+96891234567", 163, False))
        # The customer's current cards too: the till's reward-ready notice reads them (spec 2026-11-09 §2).
        self.assertEqual([c["cardId"] for c in res["cards"]], [STAMP_CARD, POINTS_CARD])

    def test_attach_new_customer_earns_and_shows_the_qr(self):
        order = self._paid_order(customer=False)
        answer = ok({"walletAdded": False, "cardUrl": CARD_URL,
                     "welcome": {"cardUrl": CARD_URL, "whatsapp": WHATSAPP, "sms": SMS}, "cards": [STAMPS]})
        with patch.object(NuqtaPassClient, "sale", return_value=self._sold("STAMPS", stamps=1)), \
                patch.object(NuqtaPassClient, "customer", return_value=answer):
            res = self.config._nuqtapass_attach(order.id, "91234567")
        self.assertEqual(res["earned"], {"cardType": "STAMPS", "stamps": 1, "points": 0})
        self.assertEqual(res["card"]["cardId"], STAMP_CARD)
        self.assertTrue(res["show_qr"])
        self.assertEqual(res["welcome"], {"cardUrl": CARD_URL, "whatsapp": WHATSAPP, "sms": SMS})

    def test_attach_scanned_card_uses_its_phone(self):
        order = self._paid_order(customer=False)
        by_card = ok({"phone": "+96894176872", "walletAdded": True, "cards": [STAMPS]})
        with patch.object(NuqtaPassClient, "customer_by_card", return_value=by_card), \
                patch.object(NuqtaPassClient, "sale", return_value=self._sold("STAMPS", stamps=1)) as sale, \
                patch.object(NuqtaPassClient, "customer", return_value=ok({"walletAdded": True, "cards": [STAMPS]})):
            res = self.config._nuqtapass_attach(order.id, STAMP_CARD)
        self.assertEqual(sale.call_args.args[0]["phone"], "+96894176872")
        self.assertEqual((res["ok"], order.nuqtapass_phone), (True, "+96894176872"))

    def test_attach_unknown_card_is_refused_and_nothing_queued(self):
        order = self._paid_order(customer=False)
        missing = ApiResult(False, 404, None, "Card not found", "CARD_NOT_FOUND", False)
        with patch.object(NuqtaPassClient, "customer_by_card", return_value=missing), \
                patch.object(NuqtaPassClient, "sale") as sale:
            res = self.config._nuqtapass_attach(order.id, STAMP_CARD)
        sale.assert_not_called()
        self.assertEqual(res["error"], "card_not_found")
        self.assertFalse(order.nuqtapass_sync_ids)
        self.assertFalse(order.nuqtapass_phone)

    def test_attach_wrong_phone_queues_nothing(self):
        order = self._paid_order(customer=False)
        self.assertEqual(self.config._nuqtapass_attach(order.id, "9417872")["error"], "invalid_phone")
        self.assertFalse(order.nuqtapass_sync_ids)

    def test_attach_twice_sends_once(self):
        order = self._paid_order(customer=False)
        with patch.object(NuqtaPassClient, "sale", return_value=self._sold()) as sale, \
                patch.object(NuqtaPassClient, "customer", return_value=ok({"walletAdded": True, "cards": []})):
            self.assertTrue(self.config._nuqtapass_attach(order.id, "91234567")["ok"])
            again = self.config._nuqtapass_attach(order.id, "98765432")
        sale.assert_called_once()
        self.assertEqual(again["error"], "already")
        self.assertEqual(order.nuqtapass_phone, "+96891234567")

    def test_attach_to_an_order_that_already_earns_is_refused(self):
        order = self._paid_order()  # paid with the customer's phone
        with patch.object(NuqtaPassClient, "sale") as sale:
            self.assertEqual(self.config._nuqtapass_attach(order.id, "98765432")["error"], "already")
        sale.assert_not_called()

    def test_attach_only_to_a_paid_sale_of_this_till(self):
        order = self._paid_order(customer=False)
        other_till = self.env["pos.config"].create({"name": "Other till"})
        draft = self.env["pos.order"].browse(self.env["pos.order"].sync_from_ui(
            [self.create_ui_order_data([(self.product, 1)], {"state": "draft"})])["pos.order"][0]["id"])
        refund = self.env["pos.order"].browse(order.refund()["res_id"])
        with patch.object(NuqtaPassClient, "sale") as sale:
            for config, order_id in ((other_till, order.id), (self.config, draft.id), (self.config, refund.id),
                                     (self.config, 999999999), (self.config, "junk")):
                with self.subTest(order_id=order_id):
                    self.assertEqual(config._nuqtapass_attach(order_id, "91234567")["error"], "bad_order")
        sale.assert_not_called()

    def test_attach_offline_keeps_the_sale_for_later(self):
        order = self._paid_order(customer=False)
        down = ApiResult(False, None, None, "Could not reach NuqtaPass", "NETWORK", True)
        with patch.object(NuqtaPassClient, "sale", return_value=down), \
                patch.object(NuqtaPassClient, "customer") as customer:
            res = self.config._nuqtapass_attach(order.id, "91234567")
        customer.assert_not_called()
        self.assertEqual((res["ok"], res["pending"], res["phone"]), (True, True, "+96891234567"))
        self.assertIn("will earn", res["message"])
        self.assertEqual(order.nuqtapass_sync_ids.state, "pending")

    # ── what the till page knows: is NuqtaPass on (the receipt box and scans only then) ─
    def test_till_page_knows_whether_nuqtapass_is_on(self):
        icp = self.env["ir.config_parameter"].sudo()
        self.assertTrue(self.config._load_pos_data_read(self.config, self.config)[0]["nuqtapass_till_on"])
        icp.set_str("nuqtapass_loyalty.api_key", False)
        self.config.invalidate_recordset()
        self.assertFalse(self.config._load_pos_data_read(self.config, self.config)[0]["nuqtapass_till_on"])
        icp.set_str("nuqtapass_loyalty.api_key", "sip_test")
        icp.set_bool("nuqtapass_loyalty.till_enabled", False)
        self.config.invalidate_recordset()
        self.assertFalse(self.config._load_pos_data_read(self.config, self.config)[0]["nuqtapass_till_on"])
