from odoo.tests import TransactionCase, tagged

from odoo.addons.nuqtapass_loyalty.lib.customer import clean_customer

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
            "points": 0, "pointsValue": 0, "balance": 0, "packUses": 0, "voucher": None,
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

    def test_handles_missing_and_bad_shapes(self):
        self.assertEqual(clean_customer(None), {"cards": [], "walletAdded": True, "welcome": None})
        self.assertEqual(clean_customer({"cards": "nope"})["cards"], [])
