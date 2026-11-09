import json

from odoo import fields, models

from odoo.addons.nuqtapass_loyalty.lib.customer import clean_customer, current_cards
from odoo.addons.nuqtapass_loyalty.lib.scan import classify

from .pos_order import PAID_STATES

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
    # Read by the till page (pos.config loads all its fields): the receipt-screen box and Wallet-card scans only
    # appear when the till switch is on and there is a key. Not the key itself: that never leaves the server.
    nuqtapass_till_on = fields.Boolean("NuqtaPass on the till", compute="_compute_nuqtapass_till_on")

    def _compute_nuqtapass_till_on(self):
        Sync = self.env["nuqtapass.sync"].sudo()
        on = Sync._channel_enabled("till") and bool(
            (self.env["ir.config_parameter"].sudo().get_str("nuqtapass_loyalty.api_key") or "").strip())
        for config in self:
            config.nuqtapass_till_on = on

    # ── the till window (called by controllers/main.py) ───────────────
    def _nuqtapass_error(self, error, message):
        return {"ok": False, "error": error, "message": message}

    def _nuqtapass_ready(self):
        """(client, None) or (None, error dict): the till switch is on and there is a key."""
        self.ensure_one()
        _ = self.env._
        Sync = self.env["nuqtapass.sync"].sudo()
        if not Sync._channel_enabled("till"):
            return None, self._nuqtapass_error("disabled", _("NuqtaPass is turned off for the till in Settings."))
        client = Sync._get_client()
        if client is None:
            return None, self._nuqtapass_error("not_configured", _("Add your NuqtaPass key in Settings first."))
        return client, None

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
        client, error = self._nuqtapass_ready()
        return (client, e164) if client else (None, error)

    def _nuqtapass_card_refused(self):
        return self._nuqtapass_error("card_not_found", self.env._("This card isn't from this shop."))

    def _nuqtapass_failure(self, result):
        _ = self.env._
        if result.status is None or result.status >= 500:
            return self._nuqtapass_error("unreachable", _(
                "NuqtaPass can't be reached right now. The sale is saved and will earn when the connection is back."))
        if result.status == 401 and result.code not in self._nuqtapass_code_words():
            return self._nuqtapass_error("refused", _("NuqtaPass refused the key. Check it in Settings."))
        if result.status == 404:
            return self._nuqtapass_error("not_found", _("No NuqtaPass card for this phone yet."))
        # By NuqtaPass's code, in the till's language (models/pos_refusal.py).
        return self._nuqtapass_refused(result)

    def _nuqtapass_lookup(self, query):
        """Find the customer by what was typed or scanned: a Wallet card's id, or a phone.

        Only the current card of each type is shown (plus usable vouchers); cards from earlier programs are hidden.
        """
        kind, value = classify(query)
        if kind == "card":
            client, error = self._nuqtapass_ready()
            if client is None:
                return error
            result = client.customer_by_card(value)
            if not result.ok:
                # 404: unknown or another shop's card (NuqtaPass answers both alike); 400: not a card id after all.
                if result.status in (400, 404):
                    return self._nuqtapass_card_refused()
                return self._nuqtapass_failure(result)
            e164 = self.env["nuqtapass.sync"].sudo()._normalise_phone((result.data or {}).get("phone"), self.company_id)
            if not e164:
                return self._nuqtapass_card_refused()
        else:
            client, e164 = self._nuqtapass_prepare(query)
            if client is None:
                return e164
            result = client.customer(e164)
            if not result.ok:
                return self._nuqtapass_failure(result)
        # clean_customer: Part 1's cards, walletAdded and, while the card isn't on a phone, the QR / WhatsApp / SMS links.
        clean = clean_customer(result.data)
        return {"ok": True, "phone": e164, **clean, "cards": current_cards(clean["cards"]),
                "canCorrect": self._nuqtapass_can_correct()}

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

    # ── sending a till sale now (after payment, or when the customer is added on the receipt screen) ─
    def _nuqtapass_order(self, order_id):
        """This till's order, or an empty recordset."""
        self.ensure_one()
        try:
            order = self.env["pos.order"].browse(int(order_id)).exists()
        except (TypeError, ValueError):
            return self.env["pos.order"]
        return order if order and order.config_id == self else self.env["pos.order"]

    def _nuqtapass_sale_row(self, order):
        return self.env["nuqtapass.sync"].sudo().search(
            [("kind", "=", "sale"), ("pos_order_id", "=", order.id)], limit=1)

    def _nuqtapass_send_now(self, sale):
        """Send the row now if this is its first send and no other transaction holds it (the cron may be sending it
        right now). A row already sent is never sent again."""
        if sale.state == "pending" and not sale.attempts and sale._claim() and not sale.attempts:
            sale._send_one()
        return sale.state == "done"

    # ── right after a till payment (static/src/app/payment/order_payment_validation.js) ─
    def _nuqtapass_after_payment(self, order_id):
        """Send this paid order's sale now, then say whether to show the card's QR code.

        Quiet on anything unexpected: the till then shows nothing, and the cron sends the order later.
        """
        order = self._nuqtapass_order(order_id)
        sale = order and self._nuqtapass_sale_row(order)
        if not sale:
            return QUIET  # no phone, or the till is switched off: nothing was queued
        if not self._nuqtapass_send_now(sale):
            return QUIET  # NuqtaPass not reached yet: no card to show; the cron retries
        client = self.env["nuqtapass.sync"].sudo()._get_client()
        if client is None:
            return QUIET
        result = client.customer(sale.phone)
        if not result.ok:
            return QUIET
        clean = clean_customer(result.data)
        if clean["walletAdded"]:
            return QUIET
        return {"ok": True, "show_qr": True, "welcome": clean["welcome"]}

    # ── the receipt screen: the customer added after paying (static/src/app/receipt_box) ─
    def _nuqtapass_attach(self, order_id, query):
        """Set the customer (a typed phone or a scanned Wallet card) on a paid order of this till and send it now.

        Answers what the order earned and where the card stands now, or the QR code for a card not on a phone yet.
        A phone NuqtaPass doesn't know yet is fine (the sale makes the customer); an unknown card is refused.
        """
        _ = self.env._
        order = self._nuqtapass_order(order_id)
        currency = order.currency_id
        if not order or order.state not in PAID_STATES or order.is_refund \
                or currency.compare_amounts(order.amount_total, 0) <= 0:
            return self._nuqtapass_error("bad_order", _("This order can't earn NuqtaPass points."))
        sale = self._nuqtapass_sale_row(order)
        if sale and not (sale.state == "failed" and sale.phone_invalid):
            return self._nuqtapass_error("already", _("This order already earns for %(phone)s.", phone=sale.phone))
        kind, _value = classify(query)
        if kind == "card":
            found = self._nuqtapass_lookup(query)
            if not found["ok"]:
                return found
            client, phone = self._nuqtapass_ready()[0], found["phone"]
        else:
            client, phone = self._nuqtapass_prepare(query)
            if client is None:
                return phone
        order.nuqtapass_phone = phone  # pos.order.write queues the sale (once)
        sale = self._nuqtapass_sale_row(order)
        if not sale or sale.state == "failed":
            return self._nuqtapass_error("bad_order", _("This order can't earn NuqtaPass points."))
        if not self._nuqtapass_send_now(sale):
            return {"ok": True, "pending": True, "phone": phone, "message": _(
                "Saved. The order will earn when NuqtaPass can be reached.")}
        try:
            answer = json.loads(sale.response_json or "{}").get("result") or {}
        except ValueError:
            answer = {}
        earned = {"cardType": answer.get("cardType"), "stamps": answer.get("stamps") or 0,
                  "points": answer.get("points") or 0}
        result = client.customer(phone)
        clean = clean_customer(result.data) if result.ok else clean_customer({})
        card = next((c for c in current_cards(clean["cards"]) if c["type"] == earned["cardType"]), None)
        return {"ok": True, "phone": phone, "earned": earned, "card": card, "cards": current_cards(clean["cards"]),
                "show_qr": not clean["walletAdded"], "welcome": clean["welcome"]}
