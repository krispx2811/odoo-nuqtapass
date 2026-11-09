from odoo import fields, models

from odoo.addons.nuqtapass_loyalty.lib.customer import clean_customer

ACTIONS = ("reward", "voucher")
QUIET = {"ok": True, "show_qr": False}
# Part 1 parseRedeemBody: points are a whole number from 1 to 10,000,000.
MAX_POINTS = 10_000_000


class PosConfig(models.Model):
    _inherit = "pos.config"

    nuqtapass_branch = fields.Char(
        "NuqtaPass branch",
        help="Branch id, code or name in NuqtaPass. Empty: NuqtaPass tags the visit 'Odoo'.",
    )

    # ── the till window (called by controllers/main.py) ───────────────
    def _nuqtapass_error(self, error, message):
        return {"ok": False, "error": error, "message": message}

    def _nuqtapass_prepare(self, phone):
        """(client, e164) or (None, error dict)."""
        self.ensure_one()
        _ = self.env._
        Sync = self.env["nuqtapass.sync"].sudo()
        if not Sync._channel_enabled("till"):
            return None, self._nuqtapass_error("disabled", _("NuqtaPass is turned off for the till in Settings."))
        e164 = Sync._normalise_phone(phone, self.company_id)
        if not e164:
            typed = str(phone or "").strip()[:32]
            return None, self._nuqtapass_error("invalid_phone", _("Phone number looks wrong: %(phone)s", phone=typed))
        client = Sync._get_client()
        if client is None:
            return None, self._nuqtapass_error("not_configured", _("Add your NuqtaPass key in Settings first."))
        return client, e164

    def _nuqtapass_failure(self, result):
        _ = self.env._
        if result.status is None or result.status >= 500:
            return self._nuqtapass_error("unreachable", _(
                "NuqtaPass can't be reached right now. The sale is saved and will earn when the connection is back."))
        if result.code == "PLAN_UPGRADE_REQUIRED":
            return self._nuqtapass_error("refused", _(
                "Odoo comes with the NuqtaPass Business plan. Ask the shop owner to upgrade on nuqtapass.com."))
        if result.code == "PLAN_ENDED":
            return self._nuqtapass_error("refused", _(
                "The shop's NuqtaPass plan has ended. The owner can renew it on nuqtapass.com."))
        if result.status == 401:
            return self._nuqtapass_error("refused", _("NuqtaPass refused the key. Check it in Settings."))
        if result.status == 404:
            return self._nuqtapass_error("not_found", _("No NuqtaPass card for this phone yet."))
        return self._nuqtapass_error("refused", result.error or _("NuqtaPass said no."))

    def _nuqtapass_lookup(self, phone):
        client, e164 = self._nuqtapass_prepare(phone)
        if client is None:
            return e164
        result = client.customer(e164)
        if not result.ok:
            return self._nuqtapass_failure(result)
        # clean_customer: Part 1's cards, walletAdded and, while the card isn't on a phone, the QR / WhatsApp / SMS links.
        return {"ok": True, "phone": e164, **clean_customer(result.data)}

    def _nuqtapass_redeem(self, phone, card_id, action, voucher_id=None, points=None):
        """POST /redeem with Part 1's body: cardId from /customer, the card's voucher id when it has one, and for a
        points reward how many points to spend (a whole number; Part 1 applies the shop's per-visit cap)."""
        _ = self.env._
        card_id = str(card_id or "").strip()
        voucher_id = str(voucher_id or "").strip()
        points_ok = points is None or (
            isinstance(points, int) and not isinstance(points, bool) and 0 < points <= MAX_POINTS)
        if action not in ACTIONS or not card_id or len(card_id) > 64 or len(voucher_id) > 64 or not points_ok \
                or (points is not None and action != "reward"):
            return self._nuqtapass_error("bad_request", _("Something is missing. Look the customer up again."))
        client, e164 = self._nuqtapass_prepare(phone)
        if client is None:
            return e164
        body = {"phone": e164, "cardId": card_id, "action": action}
        if action == "voucher" and voucher_id:
            body["voucherId"] = voucher_id
        if points is not None:
            body["points"] = points
        result = client.redeem(body)
        if not result.ok:
            return self._nuqtapass_failure(result)
        if action == "voucher":
            return {"ok": True, "message": _("Voucher used.")}
        return {"ok": True, "message": _("Points used.") if points is not None else _("Reward given.")}

    # ── right after a till payment (static/src/app/payment/order_payment_validation.js) ─
    def _nuqtapass_after_payment(self, order_id):
        """Send this paid order's sale now, then say whether to show the card's QR code.

        Quiet on anything unexpected: the till then shows nothing, and the cron sends the order later.
        """
        self.ensure_one()
        try:
            order = self.env["pos.order"].browse(int(order_id)).exists()
        except (TypeError, ValueError):
            return QUIET
        if not order or order.config_id != self:
            return QUIET
        Sync = self.env["nuqtapass.sync"].sudo()
        sale = Sync.search([("kind", "=", "sale"), ("pos_order_id", "=", order.id)], limit=1)
        if not sale:
            return QUIET  # no phone, or the till is switched off: nothing was queued
        if sale.state == "pending" and not sale.attempts:
            # Skip the send if another transaction holds the row: the cron is sending it right now.
            self.env.cr.execute("SELECT id FROM nuqtapass_sync WHERE id = %s FOR UPDATE SKIP LOCKED", [sale.id])
            if self.env.cr.fetchone():
                sale._send_one()
        if sale.state != "done":
            return QUIET  # NuqtaPass not reached yet: no card to show; the cron retries
        client = Sync._get_client()
        if client is None:
            return QUIET
        result = client.customer(sale.phone)
        if not result.ok:
            return QUIET
        clean = clean_customer(result.data)
        if clean["walletAdded"]:
            return QUIET
        return {"ok": True, "show_qr": True, "welcome": clean["welcome"]}
