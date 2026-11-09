"""Whitelist what the till window may see of a NuqtaPass GET /customer answer (Part 1 PosCustomer / PosCard).

The cards keep Part 1's field names. Besides the cards: whether the customer's card is on a phone yet
(walletAdded) and, when it isn't, the links for the QR code and the optional WhatsApp / SMS buttons. Each link
must start with the prefix NuqtaPass uses for it, or it is dropped.
"""

import re

CARD_TYPES = ("STAMPS", "POINTS", "PREPAID", "PACK", "VOUCHER")
NUMBER_KEYS = ("stamps", "stampsRequired", "points", "pointsValue", "balance", "packUses")
CARD_URL_PREFIX = "https://nuqtapass.com/"
WHATSAPP_PREFIX = "https://api.whatsapp.com/"
SMS_PREFIX = "sms:"
MAX_LINK = 2000
MAX_UNIT = 40
CURRENCY_CODE = re.compile(r"^[A-Z]{3}$")


def _number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else 0


def _number_or_none(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0 else None


def _currency(value):
    """The shop's currency at NuqtaPass ({code, symbol, decimals}): what every NuqtaPass amount on the till shows."""
    if not isinstance(value, dict) or not isinstance(value.get("code"), str) or not CURRENCY_CODE.match(value["code"]):
        return None
    decimals = value.get("decimals")
    if not isinstance(decimals, int) or isinstance(decimals, bool) or not 0 <= decimals <= 3:
        return None
    symbol = value.get("symbol")
    symbol = symbol.strip()[:8] if isinstance(symbol, str) and symbol.strip() else value["code"]
    return {"code": value["code"], "symbol": symbol, "decimals": decimals}


def _limits(value):
    """The shop's per-visit points cap (money and whole points), or None."""
    cap = value.get("pointsPerVisit") if isinstance(value, dict) else None
    if isinstance(cap, dict):
        money, points = _number_or_none(cap.get("value")), cap.get("points")
        if money is not None and isinstance(points, int) and not isinstance(points, bool) and points >= 0:
            return {"pointsPerVisit": {"value": money, "points": points}}
    return {"pointsPerVisit": None}


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
    # The card the till acts on for its type; cards from earlier programs are false. Answers from before the flag
    # have none: every card is then current.
    clean["current"] = card.get("current") is not False
    # For the payment panel: points per 1 unit of money (None: points are worth nothing), a pack's uses and unit.
    clean["pointsPerUnit"] = _number_or_none(card.get("pointsPerUnit")) or None
    clean["usesLeft"] = _number(card.get("usesLeft"))
    unit = card.get("unit")
    clean["unit"] = unit.strip()[:MAX_UNIT] if isinstance(unit, str) and unit.strip() else None
    return clean


def current_cards(cards):
    """The cards the till shows: the current card of each type, and every voucher that still has a use left.

    Vouchers are never "the card of a type" at NuqtaPass, so their flag doesn't hide them.
    """
    return [c for c in cards
            if (c["type"] == "VOUCHER" and c["voucher"] and c["voucher"]["usesLeft"] > 0)
            or (c["type"] != "VOUCHER" and c["current"])]


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
        "currency": _currency(data.get("currency")),
        "limits": _limits(data.get("limits")),
    }
