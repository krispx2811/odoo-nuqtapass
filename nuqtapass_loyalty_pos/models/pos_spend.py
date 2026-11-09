import re

from odoo import api, fields, models

# One use per kind for an order (NuqtaPass: points, credit, pack and reward once each; a voucher once per voucher card).
KINDS = ("points", "credit", "pack", "reward", "voucher")
MAX_USES = 20
MAX_POINTS = 10_000_000
MAX_MONEY = 1_000_000
MAX_PACK_USES = 10  # Part 1 MAX_USES_PER_TAP
CARD_ID = re.compile(r"^[0-9a-fA-F-]{1,64}$")
PRINTABLE = re.compile(r"^[^\x00-\x1f\x7f]{1,120}$")


def _whole(value, low, high):
    return isinstance(value, int) and not isinstance(value, bool) and low <= value <= high


def _money(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and 0 < value <= MAX_MONEY


class PosConfig(models.Model):
    _inherit = "pos.config"

    # Read by the till page (pos.config loads all its fields): the product of its NuqtaPass lines.
    nuqtapass_reward_product_id = fields.Many2one(
        "product.product", "NuqtaPass reward product", compute="_compute_nuqtapass_reward_product_id")

    def _compute_nuqtapass_reward_product_id(self):
        product = self._nuqtapass_reward_product()
        for config in self:
            config.nuqtapass_reward_product_id = product

    # ── what the module adds to the till ──────────────────────────────
    @api.model
    def _nuqtapass_reward_product(self):
        return self.env.ref("nuqtapass_loyalty_pos.product_nuqtapass_reward", raise_if_not_found=False) \
            or self.env["product.product"]

    def _get_special_products(self):
        return super()._get_special_products() | self._nuqtapass_reward_product()

    @api.model_create_multi
    def create(self, vals_list):
        configs = super().create(vals_list)
        # A new till of a company that already has NuqtaPass credit gets the method too.
        Method = self.env["pos.payment.method"].sudo()
        for config in configs:
            method = Method.search([("nuqtapass_credit", "=", True), ("company_id", "=", config.company_id.id)],
                                   limit=1)
            if method and method not in config.payment_method_ids:
                config.sudo().payment_method_ids = [(4, method.id)]
        return configs

    # ── Validate on the till: spend each use at NuqtaPass, once per order ─
    def _nuqtapass_clean_uses(self, uses):
        """The till's uses as /redeem bodies (without phone / orderRef), or None when anything is off."""
        if not isinstance(uses, list) or len(uses) > MAX_USES:
            return None
        clean, seen = [], set()
        for use in uses:
            if not isinstance(use, dict) or use.get("use") not in KINDS:
                return None
            kind, card = use["use"], str(use.get("card_id") or "").strip()
            voucher = str(use.get("voucher_id") or "").strip()
            label = str(use.get("label") or "").strip()[:200] or "NuqtaPass"
            if not CARD_ID.match(card) or (voucher and not CARD_ID.match(voucher)):
                return None
            key = (kind, card) if kind == "voucher" else kind
            if key in seen:
                return None
            seen.add(key)
            body = {"cardId": card.lower()}
            if kind == "points":
                if not _whole(use.get("points"), 1, MAX_POINTS):
                    return None
                body.update(action="reward", points=use["points"])
            elif kind == "credit":
                if not _money(use.get("amount")):
                    return None
                body.update(action="credit", amount=round(float(use["amount"]), 3))
            elif kind == "pack":
                if not _whole(use.get("uses", 1), 1, MAX_PACK_USES):
                    return None
                body.update(action="pack", uses=use.get("uses", 1))
            elif kind == "reward":
                body["action"] = "reward"
            else:
                body["action"] = "voucher"
                if voucher:
                    body["voucherId"] = voucher.lower()
            clean.append({"use": kind, "label": label, "body": body})
        return clean

    def _nuqtapass_spend(self, order_ref, phone, uses):
        """POST /redeem for each use with the order's receipt number: NuqtaPass spends each once per order.

        {"ok": True, "used": [...]} when all went through; else {"ok": False, "error", "index", "message"} and the
        till stops the payment. Uses spent before a refusal stay recorded; the next Validate sends them again and
        NuqtaPass answers them as duplicates, spending nothing more.
        """
        self.ensure_one()
        _ = self.env._
        bad = self._nuqtapass_error("bad_request", _("Something is missing. Look the customer up again."))
        order_ref = str(order_ref or "").strip()
        clean = self._nuqtapass_clean_uses(uses)
        if not PRINTABLE.match(order_ref) or clean is None:
            return bad
        if not clean:
            return {"ok": True, "used": []}
        client, e164 = self._nuqtapass_prepare(phone)
        if client is None:
            return e164
        Use = self.env["nuqtapass.pos.use"].sudo()
        used = []
        for index, use in enumerate(clean):
            body = {"phone": e164, **use["body"], "orderRef": order_ref}
            if self.nuqtapass_branch:
                body["branch"] = self.nuqtapass_branch
            result = client.redeem(body)
            if not result.ok:
                return dict(self._nuqtapass_spend_failure(result, use, order_ref), index=index)
            data = result.data or {}
            self._nuqtapass_record_use(Use, order_ref, e164, use, data)
            used.append({"index": index, "use": use["use"], "duplicate": bool(data.get("duplicate"))})
        return {"ok": True, "used": used}

    def _nuqtapass_record_use(self, Use, order_ref, phone, use, data):
        body = use["body"]
        domain = [("company_id", "=", self.company_id.id), ("order_ref", "=", order_ref), ("use", "=", use["use"]),
                  ("card_id", "=", body["cardId"])]
        if Use.search_count(domain):
            return  # a resend: NuqtaPass spent nothing more
        quantity = body.get("points") or body.get("uses") or 1
        amount = body.get("amount") or (data.get("value") if use["use"] == "points" else 0) or 0
        with self.env.cr.savepoint():
            Use.create({
                "company_id": self.company_id.id, "config_id": self.id, "order_ref": order_ref, "phone": phone,
                "use": use["use"], "card_id": body["cardId"], "voucher_id": body.get("voucherId") or False,
                "quantity": quantity, "amount": amount,
                "transaction_id": str(data.get("transactionId") or "")[:64] or False,
            })

    def _nuqtapass_spend_failure(self, result, use, order_ref):
        _ = self.env._
        if result.status is None or result.status >= 500:
            return self._nuqtapass_error("unreachable", _(
                "NuqtaPass can't be reached: remove the NuqtaPass lines to take payment without them."))
        if result.code == "IN_PROGRESS":
            return self._nuqtapass_error("busy", _(
                "NuqtaPass is still recording this order. Press Validate again in a moment."))
        if result.code == "REF_CONFLICT":
            earlier = self.env["nuqtapass.pos.use"].sudo().search([
                ("company_id", "=", self.company_id.id), ("order_ref", "=", order_ref), ("use", "=", use["use"]),
                ("card_id", "=", use["body"]["cardId"])], limit=1)
            if earlier:
                done = earlier.quantity if use["use"] in ("points", "pack") else earlier.amount
                return self._nuqtapass_error("refused", _(
                    "%(line)s: this order already used %(done)s at NuqtaPass. Set the line back to that, or remove it.",
                    line=use["label"], done=done))
        if result.status in (401, 403) or result.code in ("PLAN_UPGRADE_REQUIRED", "PLAN_ENDED"):
            failure = self._nuqtapass_failure(result)  # the key or the plan: the same words as the look-up
            return failure
        return self._nuqtapass_error("refused", _(
            "%(line)s: %(reason)s. Remove this line to take payment without it.",
            line=use["label"], reason=(result.error or _("NuqtaPass said no")).rstrip(". ")))
