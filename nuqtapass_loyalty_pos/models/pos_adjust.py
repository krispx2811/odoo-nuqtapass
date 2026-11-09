from odoo import models

# Part 1 POST /adjust (spec 2026-11-09 "tiers, reward-ready alert, corrections" §3).
ACTIONS = ("stamp_add", "stamp_undo", "points")
MANAGER_GROUP = "point_of_sale.group_pos_manager"  # "Point of Sale / Administrator" (Odoo 19 and 20)
REASON_MIN, REASON_MAX = 3, 200
MAX_DELTA = 1_000_000


def _points(n):
    return f"{n:,}"


class PosConfig(models.Model):
    _inherit = "pos.config"

    def _nuqtapass_can_correct(self):
        return self.env.user.has_group(MANAGER_GROUP)

    def _nuqtapass_adjust(self, card_id, action, delta, reason):
        """A correction from the till: one stamp on or off, or ± points, always with a reason.

        Only "Point of Sale / Administrator" users (checked here, not only on the till). The Activity log at NuqtaPass
        gets the reason and this Odoo user's name, never a name sent by the browser.
        """
        self.ensure_one()
        _ = self.env._
        if not self._nuqtapass_can_correct():
            return self._nuqtapass_error("not_allowed", _("Only Point of Sale administrators can correct cards."))
        card_id = str(card_id or "").strip().lower()
        if action not in ACTIONS or not card_id or len(card_id) > 64:
            return self._nuqtapass_error("bad_request", _("Something is missing. Look the customer up again."))
        reason = reason.strip() if isinstance(reason, str) else ""
        if not REASON_MIN <= len(reason) <= REASON_MAX:
            return self._nuqtapass_error("bad_reason", _("Write why, in 3 to 200 characters."))
        whole = isinstance(delta, int) and not isinstance(delta, bool)
        if action == "points" and not (whole and delta != 0 and abs(delta) <= MAX_DELTA):
            return self._nuqtapass_error("bad_delta", _("Points: a whole number other than 0, like 50 or -50."))
        client, error = self._nuqtapass_ready()
        if client is None:
            return error
        body = {"cardId": card_id, "action": action, "reason": reason, "staffName": (self.env.user.name or "")[:120]}
        if action == "points":
            body["delta"] = delta
        result = client.adjust(body)
        if not result.ok:
            if result.status == 404:
                return self._nuqtapass_card_refused()
            return self._nuqtapass_failure(result)
        return {"ok": True, "message": self._nuqtapass_adjusted(action, delta, result.data or {})}

    def _nuqtapass_adjusted(self, action, asked, data):
        _ = self.env._
        if action != "points":
            words = {"stamps": data.get("stamps", 0), "required": data.get("stampsRequired", 0)}
            if action == "stamp_add":
                return _("Stamp added: %(stamps)s of %(required)s now.", **words)
            return _("Stamp taken off: %(stamps)s of %(required)s now.", **words)
        # "+50" / "-40" after a label: no plural forms, and the number reads right in Arabic too.
        applied, total = data.get("delta") or 0, _points(data.get("points") or 0)
        if applied == 0:
            return _("The card has no points to take off.")
        change = f"\u2066{applied:+,}\u2069"  # isolated: the sign stays before the number in Arabic
        if applied < 0 and -applied < -asked:
            return _("Points corrected: %(change)s (all the card had) · %(total)s now.", change=change, total=total)
        return _("Points corrected: %(change)s · %(total)s now.", change=change, total=total)
