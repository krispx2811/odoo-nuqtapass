"""NuqtaPass's refusals in the till's language, by their error code.

NuqtaPass answers in English with a `code`. A known code gets the module's own words (English and Gulf Arabic, the
words the NuqtaPass website and staff app use for the same codes: apps/staff/src/lib/odoo.ts failedReason and
lib/apiError.ts). A few refusals come without a code (not enough points, the per-visit cap, not enough credit or pack
uses, a stamp card not full yet, no stamp to undo): they are known by the start of NuqtaPass's English sentence; an
English till keeps that sentence (it names the balance or the cap), an Arabic one gets the module's words. Anything
else: an English till shows NuqtaPass's sentence; an Arabic till a plain Arabic line, with NuqtaPass's sentence only
as `detail` (the till's tooltip), so no English sentence shows as the line.
"""

import re

from odoo import models

# NuqtaPass's own English sentences for the refusals it sends without a code (apps/api/src/services/cardService.ts,
# balanceService.ts). A changed sentence falls back to the unknown-code words: never a wrong translation.
UNCODED = tuple((re.compile(pattern), key) for pattern, key in (
    (r"^Not enough points\b", "NOT_ENOUGH_POINTS"),
    (r"^Per-visit limit is\b", "POINTS_CAP"),
    (r"^Not enough credit\b", "NOT_ENOUGH_CREDIT"),
    (r"^(No uses left|Only \d+ left) on this pack\b", "NO_USES_LEFT"),
    (r"^Need \d+ stamps to redeem\b", "NOT_FULL"),
    (r"^No stamps to undo\b", "NO_STAMP_TO_UNDO"),
    (r"^Loyalty is not enabled\b", "LOYALTY_NOT_ENABLED"),
))


class PosConfig(models.Model):
    _inherit = "pos.config"

    def _nuqtapass_till_is_arabic(self):
        return (self.env.lang or "").startswith("ar")

    def _nuqtapass_code_words(self):
        """{code: the till's words}. Built per call so each string is translated in the user's language."""
        _ = self.env._
        reason = _("Write why, in 3 to 200 characters.")
        plan = _("Odoo comes with the NuqtaPass Business plan. Ask the shop owner to upgrade on nuqtapass.com.")
        ended = _("The shop's NuqtaPass access has ended. The owner can renew it on nuqtapass.com.")
        busy = _("NuqtaPass is still recording this order. Try again in a moment.")
        return {
            "CARD_FULL": _("This card is full. Give the reward first, then add stamps again."),
            "CARD_INACTIVE": _("This card isn't active any more (it was used up or has expired)."),
            "CARD_NOT_FOUND": _("That card wasn't found at this shop."),
            "OTHER_SHOP": _("That card belongs to another shop."),
            "CARD_MISMATCH": _("This card changed at NuqtaPass. Look the customer up again."),
            "VOUCHER_MISMATCH": _("This voucher changed at NuqtaPass. Look the customer up again."),
            "WRONG_CARD_TYPE": _("This card is a different type, so it can't do that."),
            "POINTS_TOO_SMALL": _("That amount is too small to earn a point."),
            "VOUCHER_SAME_PHONE": _("This iPhone already used this offer."),
            "REF_CONFLICT": _("This order already used a different amount at NuqtaPass."),
            "IN_PROGRESS": busy,
            "DUPLICATE_RACE": busy,
            "ORDER_REFUNDED": _("This order was refunded, so nothing more can be used on it."),
            "NOT_ADJUSTABLE": _("Credit and pack uses can't be corrected here: they change with sales and refunds."),
            "MISSING_REASON": reason,
            "INVALID_REASON": reason,
            "INVALID_DELTA": _("Points: a whole number other than 0, like 50 or -50."),
            "PLAN_UPGRADE_REQUIRED": plan,
            "PLAN_LIMIT_REACHED": plan,
            "PLAN_ENDED": _("The shop's NuqtaPass plan has ended. The owner can renew it on nuqtapass.com."),
            "SUBSCRIPTION_EXPIRED": ended,
            "ACCESS_EXPIRED": ended,
            "SHOP_PAUSED": _("The shop is paused at NuqtaPass, so the till can't use cards for now."),
            "SHOP_SUSPENDED": ended,
            "LOYALTY_NOT_ENABLED": _("Loyalty cards are off for this shop at NuqtaPass."),
            "RATE_LIMITED": _("Too many tries. Wait a minute and try again."),
            # Without a code at NuqtaPass (UNCODED): only an Arabic till uses these.
            "NOT_ENOUGH_POINTS": _("The card doesn't have enough points."),
            "POINTS_CAP": _("That's more than the shop's points limit for one visit."),
            "NOT_ENOUGH_CREDIT": _("The card doesn't have enough credit."),
            "NO_USES_LEFT": _("The pack doesn't have that many uses left."),
            "NOT_FULL": _("The stamp card isn't full yet."),
            "NO_STAMP_TO_UNDO": _("There's no stamp to take off."),
        }

    def _nuqtapass_refusal(self, result):
        """(the till's line, detail or None) for a NuqtaPass refusal (an ApiResult that isn't ok)."""
        _ = self.env._
        server = (result.error or "").strip()
        words = self._nuqtapass_code_words()
        code = result.code if isinstance(result.code, str) else ""
        if code in words:
            return words[code], None
        if code.startswith("INVALID_"):
            return _("Something is missing. Look the customer up again."), None
        arabic = self._nuqtapass_till_is_arabic()
        if not code:
            known = next((key for pattern, key in UNCODED if pattern.match(server)), None)
            if known:
                return (words[known], None) if arabic else (server, None)
        if arabic or not server:
            return _("We couldn't finish this. Try again."), (server or None)
        return server, None

    def _nuqtapass_refused(self, result, error="refused"):
        """The till's error dict for a refusal: its line, and NuqtaPass's own words as `detail` when only an Arabic
        line stands in for them."""
        text, detail = self._nuqtapass_refusal(result)
        answer = self._nuqtapass_error(error, text)
        if detail:
            answer["detail"] = detail
        return answer
