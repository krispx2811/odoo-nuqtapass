from odoo.tests import TransactionCase, tagged

from odoo.addons.nuqtapass_loyalty.lib.customer import clean_customer, current_cards

CARD_URL = "https://nuqtapass.com/join/qahwa"
WHATSAPP = "https://api.whatsapp.com/send?phone=96891234567&text=Welcome"
SMS = "sms:+96891234567?body=Welcome"
STAMP_CARD = "cccccccc-1111-4111-8111-111111111111"
VOUCHER_CARD = "dddddddd-1111-4111-8111-111111111111"
VOUCHER = "eeeeeeee-1111-4111-8111-111111111111"


def part1_answer(**over):
    """A GET /api/pos/customer `data`, exactly as Part 1's getPosCustomer returns it."""
    data = {
        "phone": "+96891234567",
        "walletAdded": True,
        "cardUrl": None,
        "welcome": None,
        "cards": [
            {"cardId": STAMP_CARD, "type": "STAMPS", "stamps": 6, "stampsRequired": 6, "rewardReady": True,
             "points": 0, "pointsValue": 0, "balance": 0, "packUses": 0, "voucher": None},
            {"cardId": VOUCHER_CARD, "type": "VOUCHER", "stamps": 0, "stampsRequired": 6, "rewardReady": False,
             "points": 0, "pointsValue": 0, "balance": 0, "packUses": 0,
             "voucher": {"id": VOUCHER, "title": "Free coffee", "usesLeft": 1}},
        ],
    }
    data.update(over)
    return data


@tagged("post_install", "-at_install", "nuqtapass")
class TestCustomer(TransactionCase):
    def test_keeps_part1_cards_as_they_are(self):
        clean = clean_customer(part1_answer())
        self.assertEqual(clean["cards"][0], {
            "cardId": STAMP_CARD, "type": "STAMPS", "stamps": 6, "stampsRequired": 6, "rewardReady": True,
            "points": 0, "pointsValue": 0, "balance": 0, "packUses": 0, "voucher": None, "current": True,
            "pointsPerUnit": None, "usesLeft": 0, "unit": None,
        })
        self.assertEqual(clean["cards"][1]["voucher"], {"id": VOUCHER, "title": "Free coffee", "usesLeft": 1})
        self.assertTrue(clean["walletAdded"])
        self.assertIsNone(clean["welcome"])
        self.assertNotIn("phone", clean)

    def test_drops_unknown_fields_types_and_cards_without_id(self):
        data = part1_answer(cards=[
            {"cardId": STAMP_CARD, "type": "STAMPS", "stamps": 2, "deviceKeyHash": "secret"},
            {"cardId": VOUCHER_CARD, "type": "GIFT"},
            {"type": "POINTS", "points": 9},
            "x",
        ])
        cards = clean_customer(data)["cards"]
        self.assertEqual([c["cardId"] for c in cards], [STAMP_CARD])
        self.assertNotIn("deviceKeyHash", cards[0])
        self.assertEqual(cards[0]["points"], 0)
        self.assertFalse(cards[0]["rewardReady"])

    def test_a_legacy_voucher_has_no_id(self):
        card = dict(part1_answer()["cards"][1], voucher={"id": None, "title": "Old offer", "usesLeft": 2})
        clean = clean_customer(part1_answer(cards=[card]))
        self.assertEqual(clean["cards"][0]["voucher"], {"id": None, "title": "Old offer", "usesLeft": 2})

    def test_card_not_on_a_phone_keeps_the_links(self):
        clean = clean_customer(part1_answer(
            walletAdded=False, cardUrl=CARD_URL,
            welcome={"cardUrl": CARD_URL, "whatsapp": WHATSAPP, "sms": SMS, "message": "Welcome"},
        ))
        self.assertFalse(clean["walletAdded"])
        self.assertEqual(clean["welcome"], {"cardUrl": CARD_URL, "whatsapp": WHATSAPP, "sms": SMS})

    def test_unsafe_links_are_dropped(self):
        # No safe card link: nothing to show, so no QR code.
        clean = clean_customer(part1_answer(walletAdded=False, cardUrl="javascript:alert(1)"))
        self.assertTrue(clean["walletAdded"])
        self.assertIsNone(clean["welcome"])
        # A safe card link keeps the QR code; bad WhatsApp / SMS links are dropped on their own.
        clean = clean_customer(part1_answer(walletAdded=False, cardUrl=CARD_URL,
                                            welcome={"whatsapp": "javascript:x", "sms": "https://evil.example"}))
        self.assertEqual(clean["welcome"], {"cardUrl": CARD_URL, "whatsapp": None, "sms": None})
        clean = clean_customer(part1_answer(walletAdded=False, cardUrl="https://evil.example/join/qahwa"))
        self.assertIsNone(clean["welcome"])

    def test_only_an_explicit_false_shows_the_qr(self):
        self.assertIsNone(clean_customer({"cardUrl": CARD_URL})["welcome"])
        self.assertIsNone(clean_customer({"walletAdded": "false", "cardUrl": CARD_URL})["welcome"])

    def test_current_flag_kept_and_missing_means_current(self):
        old_points = {"cardId": "aaaaaaaa-0000-4000-8000-000000000000", "type": "POINTS", "points": 40,
                      "current": False}
        cards = clean_customer(part1_answer(cards=[old_points, part1_answer()["cards"][0]]))["cards"]
        self.assertEqual([c["current"] for c in cards], [False, True])  # an answer from before `current`
        bad = clean_customer(part1_answer(cards=[dict(old_points, current="no")]))["cards"]
        self.assertTrue(bad[0]["current"])  # only an explicit false hides a card

    def test_current_cards_hide_earlier_programs_but_keep_usable_vouchers(self):
        stamp, voucher = part1_answer()["cards"]
        cards = clean_customer(part1_answer(cards=[
            {"cardId": "aaaaaaaa-0000-4000-8000-000000000000", "type": "POINTS", "points": 40, "current": False},
            dict(stamp, current=True),
            # Vouchers are never "the card of a type", so their flag doesn't hide them; used-up ones go.
            dict(voucher, current=False),
            dict(voucher, cardId="dddddddd-2222-4222-8222-222222222222",
                 voucher={"id": VOUCHER, "title": "Used", "usesLeft": 0}),
        ]))["cards"]
        self.assertEqual([c["cardId"] for c in current_cards(cards)], [STAMP_CARD, VOUCHER_CARD])

    def test_handles_missing_and_bad_shapes(self):
        self.assertEqual(clean_customer(None), {"cards": [], "walletAdded": True, "welcome": None, "currency": None,
                                                "limits": {"pointsPerVisit": None}})
        self.assertEqual(clean_customer({"cards": "nope"})["cards"], [])

    # ── what the payment panel needs (added 2026-11-09: uses at payment) ─
    def test_keeps_currency_limits_and_card_money_fields(self):
        points = {"cardId": "aaaaaaaa-2222-4222-8222-222222222222", "type": "POINTS", "points": 1404,
                  "pointsValue": 42.12, "pointsPerUnit": 33.333333, "usesLeft": 0, "unit": None}
        pack = {"cardId": "bbbbbbbb-2222-4222-8222-222222222222", "type": "PACK", "packUses": 4, "usesLeft": 4,
                "unit": "visits", "pointsPerUnit": None}
        clean = clean_customer(part1_answer(
            currency={"code": "OMR", "symbol": "OMR", "decimals": 3},
            limits={"pointsPerVisit": {"value": 10, "points": 333}}, cards=[points, pack]))
        self.assertEqual(clean["currency"], {"code": "OMR", "symbol": "OMR", "decimals": 3})
        self.assertEqual(clean["limits"], {"pointsPerVisit": {"value": 10, "points": 333}})
        self.assertEqual((clean["cards"][0]["pointsPerUnit"], clean["cards"][0]["unit"]), (33.333333, None))
        self.assertEqual((clean["cards"][1]["usesLeft"], clean["cards"][1]["unit"], clean["cards"][1]["pointsPerUnit"]),
                         (4, "visits", None))

    def test_bad_currency_and_limits_are_dropped(self):
        for bad in ({"code": "<b>", "symbol": "OMR", "decimals": 3}, {"code": "OMR", "symbol": "OMR", "decimals": 9},
                    {"code": "OMR", "decimals": True}, "OMR", None):
            with self.subTest(bad=bad):
                self.assertIsNone(clean_customer(part1_answer(currency=bad))["currency"])
        clean = clean_customer(part1_answer(limits={"pointsPerVisit": {"value": "10", "points": -1}}))
        self.assertEqual(clean["limits"], {"pointsPerVisit": None})
        self.assertEqual(clean_customer(part1_answer())["limits"], {"pointsPerVisit": None})
        card = dict(part1_answer()["cards"][0], pointsPerUnit="x", unit="v" * 500)
        cleaned = clean_customer(part1_answer(cards=[card]))["cards"][0]
        self.assertIsNone(cleaned["pointsPerUnit"])
        self.assertEqual(len(cleaned["unit"]), 40)

    # ── tiers (2026-11-09): the current points card's tier, whitelisted ─
    def _points(self, **over):
        return dict({"cardId": "aaaaaaaa-2222-4222-8222-222222222222", "type": "POINTS", "points": 1404,
                     "current": True}, **over)

    def test_keeps_a_good_tier(self):
        tier = {"name": "SILVER", "cashbackPct": 7.5, "next": {"name": "GOLD", "pointsToGo": 3800},
                "color": "rgb(213, 220, 228)"}
        card = clean_customer(part1_answer(cards=[self._points(tier=tier)]))["cards"][0]
        self.assertEqual(card["tier"], tier)
        gold = {"name": "GOLD", "cashbackPct": 10, "next": None}
        card = clean_customer(part1_answer(cards=[self._points(tier=gold)]))["cards"][0]
        self.assertEqual(card["tier"], {"name": "GOLD", "cashbackPct": 10, "next": None, "color": None})

    def test_no_tier_key_without_one(self):
        self.assertNotIn("tier", clean_customer(part1_answer())["cards"][0])
        self.assertNotIn("tier", clean_customer(part1_answer(cards=[self._points()]))["cards"][0])

    def test_bad_tiers_are_dropped(self):
        for bad in ({"name": "PLATINUM", "cashbackPct": 5, "next": None},
                    {"name": "GOLD", "cashbackPct": -1, "next": None},
                    {"name": "GOLD", "cashbackPct": "10", "next": None},
                    {"name": "GOLD", "cashbackPct": 101, "next": None},
                    {"name": "BRONZE", "cashbackPct": 5, "next": {"name": "BRONZE", "pointsToGo": 3}},
                    {"name": "BRONZE", "cashbackPct": 5, "next": {"name": "SILVER", "pointsToGo": -3}},
                    {"name": "BRONZE", "cashbackPct": 5, "next": {"name": "SILVER", "pointsToGo": 2.5}},
                    "GOLD", None):
            with self.subTest(bad=bad):
                card = clean_customer(part1_answer(cards=[self._points(tier=bad)]))["cards"][0]
                self.assertNotIn("tier", card)

    def test_an_unsafe_tier_colour_is_dropped_not_the_tier(self):
        for color in ("red;background:url(x)", "rgb(1, 2, 3);x", "#fff", 5):
            with self.subTest(color=color):
                tier = {"name": "GOLD", "cashbackPct": 10, "next": None, "color": color}
                card = clean_customer(part1_answer(cards=[self._points(tier=tier)]))["cards"][0]
                self.assertIsNone(card["tier"]["color"])
