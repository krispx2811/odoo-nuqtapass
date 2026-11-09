"""What a till scan or a typed value is.

A NuqtaPass Wallet card's QR holds the card's id (a UUID); passes made before that hold the customer's phone. The
till sends a card id to `GET /customer?card=`, a phone to `?phone=`, and leaves anything else to Odoo (product
barcodes). Same shapes as `static/src/app/nuqtapass_api.js` scanKind().
"""
import re

CARD_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)
# 8-15 digits once spaces and dashes are gone, with an optional "+" (or the "00" international prefix).
PHONE = re.compile(r"^\+?\d{8,15}$")
SEPARATORS = re.compile(r"[\s-]")


def classify(text):
    """("card", lower-case id), ("phone", the text as typed) or (None, None)."""
    text = str(text or "").strip()
    if CARD_ID.match(text):
        return "card", text.lower()
    digits = SEPARATORS.sub("", text)
    if digits.startswith("00"):
        digits = digits[2:]
    if PHONE.match(digits):
        return "phone", text
    return None, None
