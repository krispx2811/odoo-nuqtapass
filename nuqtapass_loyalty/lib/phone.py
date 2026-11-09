"""Phone numbers → E.164 ("+96891234567"), using the company's country code.

Kept dependency-free (no `phonenumbers`, which Odoo treats as optional).
NuqtaPass validates the number again on its side.
"""
import re

_NON_DIGITS = re.compile(r"\D")


def normalise_e164(raw, calling_code):
    """Return "+<8-15 digits>" or None when the number can't be used.

    :param raw: what was typed (spaces, dashes, "00" or "+" prefixes allowed)
    :param calling_code: the company country's phone code (int, e.g. 968) or None
    """
    if not raw:
        return None
    text = str(raw).strip()
    digits = _NON_DIGITS.sub("", text)
    if not digits:
        return None
    code = str(calling_code or "").strip()

    if text.startswith("+"):
        full = digits
    elif digits.startswith("00"):
        full = digits[2:]
    elif not code:
        return None
    elif digits.startswith(code) and not digits.startswith("0") and len(digits) - len(code) >= 7:
        full = digits
    else:
        full = code + digits.lstrip("0")

    if full.startswith("0") or not 8 <= len(full) <= 15:
        return None
    return "+" + full
