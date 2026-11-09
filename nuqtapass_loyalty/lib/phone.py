"""Phone numbers → E.164 ("+96891234567"), only when the number is a real mobile number for its country.

A number that only looks like a phone ("9417872": an Omani mobile missing a digit) must never reach NuqtaPass,
which would make a customer for it. Two ways to check, same answers:

- `phonenumbers` (what Odoo's own phone_validation uses; the odoo:20.0 image ships it): the number must be valid
  and a mobile (or a number type that can be a mobile), read with the company's country as the default.
- Without it (Odoo treats it as optional, so it is not a dependency here): the national length must match for
  the countries NuqtaPass shops are in (GCC + Jordan); other countries keep the old 8-15 digit rule.
"""
import re

try:
    import phonenumbers
except ImportError:  # optional in Odoo: fall back to the length table
    phonenumbers = None

_NON_DIGITS = re.compile(r"\D")
_LETTERS = re.compile(r"[^\W\d_]")
# Calling code → digits after it, for mobiles (Oman, UAE, KSA, Kuwait, Qatar, Bahrain, Jordan).
NATIONAL_LENGTH = {"968": 8, "971": 9, "966": 9, "965": 8, "974": 8, "973": 8, "962": 9}


def normalise_e164(raw, region=None, calling_code=None):
    """Return "+<digits>" for a valid mobile number, or None when it can't be used.

    :param raw: what was typed (spaces, dashes, "00" or "+" prefixes allowed)
    :param region: the company country's ISO code ("OM") or None
    :param calling_code: the company country's phone code (968) or None
    """
    if not raw:
        return None
    text = str(raw).strip()
    digits = _NON_DIGITS.sub("", text)
    if not digits:
        return None
    if not text.startswith("+") and digits.startswith("00"):
        text, digits = "+" + digits[2:], digits[2:]
    if phonenumbers is not None:
        return _with_library(text, region)
    return _with_table(text, digits, str(calling_code or "").strip())


def _with_library(text, region):
    if not text.startswith("+") and not region:
        return None
    try:
        number = phonenumbers.parse(text, (region or "").upper() or None)
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_valid_number(number):
        return None
    mobile = (phonenumbers.PhoneNumberType.MOBILE, phonenumbers.PhoneNumberType.FIXED_LINE_OR_MOBILE)
    if phonenumbers.number_type(number) not in mobile:
        return None
    return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)


def _with_table(text, digits, code):
    if _LETTERS.search(text):
        return None
    if text.startswith("+"):
        full = digits
    elif not code:
        return None
    else:
        national = NATIONAL_LENGTH.get(code)
        typed_code = digits.startswith(code) and not digits.startswith("0")
        if typed_code and (len(digits) - len(code) == national if national else len(digits) - len(code) >= 7):
            full = digits
        else:
            full = code + digits.lstrip("0")
    if full.startswith("0") or not 8 <= len(full) <= 15:
        return None
    national = NATIONAL_LENGTH.get(full[:3])
    if national and len(full) - 3 != national:
        return None
    return "+" + full
