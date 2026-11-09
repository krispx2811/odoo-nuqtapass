"""Whitelist what the till window may see of a NuqtaPass GET /customer answer (Part 1 PosCustomer / PosCard).

The cards keep Part 1's field names. Besides the cards: whether the customer's card is on a phone yet
(walletAdded) and, when it isn't, the links for the QR code and the optional WhatsApp / SMS buttons. Each link
must start with the prefix NuqtaPass uses for it, or it is dropped.
"""

CARD_TYPES = ("STAMPS", "POINTS", "PREPAID", "PACK", "VOUCHER")
NUMBER_KEYS = ("stamps", "stampsRequired", "points", "pointsValue", "balance", "packUses")
CARD_URL_PREFIX = "https://nuqtapass.com/"
WHATSAPP_PREFIX = "https://api.whatsapp.com/"
SMS_PREFIX = "sms:"
MAX_LINK = 2000


def _number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else 0


def _link(value, prefix):
    if isinstance(value, str) and value.startswith(prefix) and len(value) <= MAX_LINK:
        return value
    return None


def _card(card):
    if not isinstance(card, dict) or not isinstance(card.get("cardId"), str) or not card["cardId"]:
        return None
    if card.get("type") not in CARD_TYPES:
        return None
    clean = {"cardId": card["cardId"][:64], "type": card["type"], "rewardReady": card.get("rewardReady") is True}
    for key in NUMBER_KEYS:
        clean[key] = _number(card.get(key))
    voucher = card.get("voucher") if isinstance(card.get("voucher"), dict) else None
    clean["voucher"] = {
        "id": str(voucher["id"])[:64] if voucher.get("id") else None,
        "title": str(voucher.get("title") or "")[:200],
        "usesLeft": _number(voucher.get("usesLeft")),
    } if voucher else None
    return clean


def clean_customer(data):
    data = data if isinstance(data, dict) else {}
    raw_cards = data.get("cards") if isinstance(data.get("cards"), list) else []
    cards = [c for c in (_card(card) for card in raw_cards) if c]
    welcome = data.get("welcome") if isinstance(data.get("welcome"), dict) else {}
    card_url = _link(data.get("cardUrl") or welcome.get("cardUrl"), CARD_URL_PREFIX)
    # Only an explicit false, with a safe card link, shows the QR code.
    show_qr = data.get("walletAdded") is False and card_url is not None
    return {
        "cards": cards,
        "walletAdded": not show_qr,
        "welcome": {
            "cardUrl": card_url,
            "whatsapp": _link(welcome.get("whatsapp"), WHATSAPP_PREFIX),
            "sms": _link(welcome.get("sms"), SMS_PREFIX),
        } if show_qr else None,
    }
