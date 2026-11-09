import json
import logging
from datetime import timezone

from odoo import api, fields, models

from odoo.addons.nuqtapass_loyalty.lib.backoff import next_retry_delay
from odoo.addons.nuqtapass_loyalty.lib.client import DEFAULT_BASE_URL, ApiResult, NuqtaPassClient
from odoo.addons.nuqtapass_loyalty.lib.phone import normalise_e164

_logger = logging.getLogger(__name__)

PARAM_KEY = "nuqtapass_loyalty.api_key"
PARAM_BASE_URL = "nuqtapass_loyalty.base_url"
CRON_XMLID = "nuqtapass_loyalty.ir_cron_nuqtapass_send"
# What is kept of a Part 1 PosAnswer's `result` (no card id, links or balances).
RESULT_KEYS = ("cardType", "stamps", "points", "shortfall", "reason")


class NuqtapassSync(models.Model):
    """One order or refund to send to NuqtaPass. The only NuqtaPass data kept in Odoo."""

    _name = "nuqtapass.sync"
    _description = "NuqtaPass sync"
    _order = "id desc"
    _rec_name = "order_ref"

    company_id = fields.Many2one("res.company", required=True, default=lambda s: s.env.company, index=True)
    kind = fields.Selection([("sale", "Sale"), ("refund", "Refund")], required=True, readonly=True)
    channel = fields.Selection([("till", "Till"), ("online", "Online store")], required=True, readonly=True)
    state = fields.Selection(
        [("pending", "Waiting to send"), ("done", "Sent"), ("failed", "Failed")],
        default="pending", required=True, index=True, readonly=True,
    )
    order_ref = fields.Char("Order", required=True, readonly=True)
    refund_ref = fields.Char("Refund", readonly=True)
    dedupe_key = fields.Char(required=True, readonly=True)
    phone = fields.Char(readonly=True)
    phone_invalid = fields.Boolean(
        "Phone looks wrong", readonly=True,
        help="Not a valid mobile number for its country, so it is not sent. Fix the phone and press Resend.")
    amount = fields.Monetary(readonly=True, currency_field="currency_id")
    currency_id = fields.Many2one("res.currency", default=lambda s: s.env.company.currency_id, readonly=True)
    occurred_at = fields.Datetime("Paid / refunded at", required=True, readonly=True)
    branch = fields.Char(readonly=True)
    customer_name = fields.Char(readonly=True)
    attempts = fields.Integer(readonly=True)
    next_attempt_at = fields.Datetime("Next try", index=True, readonly=True)
    last_error = fields.Char(readonly=True)
    last_status_code = fields.Integer(readonly=True)
    response_json = fields.Text("NuqtaPass answer", readonly=True)
    summary = fields.Char("NuqtaPass", compute="_compute_summary")

    _dedupe_unique = models.Constraint(
        "UNIQUE(company_id, dedupe_key)", "This order or refund is already queued for NuqtaPass."
    )

    # ── settings helpers ──────────────────────────────────────────────
    @api.model
    def _channel_enabled(self, channel):
        # Odoo 20: typed parameters (get_bool); a missing parameter means "off".
        return self.env["ir.config_parameter"].sudo().get_bool(f"nuqtapass_loyalty.{channel}_enabled")

    @api.model
    def _normalise_phone(self, raw, company):
        country = company.country_id
        return normalise_e164(raw, country.code or None, country.phone_code or None)

    @api.model
    def _sale_phone_vals(self, raw, company):
        """{} without a phone (nothing to queue), {"phone": e164}, or the typed phone flagged as wrong."""
        raw = (raw or "").strip()
        if not raw:
            return {}
        e164 = self._normalise_phone(raw, company)
        return {"phone": e164} if e164 else {"phone": raw, "phone_invalid": True}

    def _wrong_phone_vals(self, phone):
        return {"phone": phone, "phone_invalid": True, "state": "failed", "next_attempt_at": False,
                "last_status_code": 0,
                "last_error": self.env._("Phone number looks wrong: %(phone)s", phone=phone)}

    @api.model
    def _make_client(self, key):
        base = self.env["ir.config_parameter"].sudo().get_str(PARAM_BASE_URL) or DEFAULT_BASE_URL
        return NuqtaPassClient(key.strip(), base)

    @api.model
    def _get_client(self):
        key = (self.env["ir.config_parameter"].sudo().get_str(PARAM_KEY) or "").strip()
        if not key:
            return None
        try:
            return self._make_client(key)
        except ValueError:
            _logger.warning("NuqtaPass: bad base URL setting, not sending")
            return None

    # ── queue ─────────────────────────────────────────────────────────
    @api.model
    def _dedupe(self, vals):
        return "|".join((vals["kind"], vals["order_ref"], vals.get("refund_ref") or ""))

    @api.model
    def _queue(self, vals):
        """Queue a sale/refund once. Callers wrap this in try/except: a sale must never fail on us."""
        vals = dict(vals)
        if vals["kind"] == "sale" and not vals.get("phone"):
            raise ValueError("A NuqtaPass sale needs a phone")
        if vals["kind"] == "refund" and not vals.get("refund_ref"):
            raise ValueError("A NuqtaPass refund needs refund_ref")
        vals.setdefault("company_id", self.env.company.id)
        vals["dedupe_key"] = self._dedupe(vals)
        existing = self.search(
            [("company_id", "=", vals["company_id"]), ("dedupe_key", "=", vals["dedupe_key"])], limit=1
        )
        if existing:
            return existing
        if vals.get("phone_invalid"):
            # Logged so staff can see it on the order, never sent: NuqtaPass would make a customer for it.
            vals.update(self._wrong_phone_vals(vals["phone"]))
            with self.env.cr.savepoint():
                return self.create(vals)
        vals.setdefault("next_attempt_at", fields.Datetime.now())
        with self.env.cr.savepoint():
            record = self.create(vals)
        cron = self.sudo().env.ref(CRON_XMLID, raise_if_not_found=False)
        if cron:
            cron._trigger()
        return record

    # ── payload ───────────────────────────────────────────────────────
    def _iso(self, value):
        return value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")

    def _payload(self):
        self.ensure_one()
        digits = self.currency_id.decimal_places if self.currency_id else 3
        amount = round(self.amount, digits)
        if self.kind == "sale":
            body = {
                "source": "odoo",
                "channel": self.channel,
                "orderRef": self.order_ref,
                "phone": self.phone,
                "amount": amount,
                "paidAt": self._iso(self.occurred_at),
            }
            if self.branch:
                body["branch"] = self.branch
            if self.customer_name:
                body["customerName"] = self.customer_name
            return body
        return {
            "source": "odoo",
            "orderRef": self.order_ref,
            "refundRef": self.refund_ref,
            "amount": amount,
            "refundedAt": self._iso(self.occurred_at),
        }

    # ── sending ───────────────────────────────────────────────────────
    def _send_one(self, now=None):
        self.ensure_one()
        now = now or fields.Datetime.now()
        if self.kind == "sale" and not self._normalise_phone(self.phone, self.company_id):
            # Also catches rows queued before phones were checked.
            self.write(dict(self._wrong_phone_vals(self.phone), attempts=self.attempts + 1))
            return
        client = self._get_client()
        if client is None:
            result = ApiResult(False, None, None, self.env._("No NuqtaPass key in Settings"),
                               "NOT_CONFIGURED", True)
        elif self.kind == "sale":
            result = client.sale(self._payload())
        else:
            result = client.refund(self._payload())

        if result.ok and (result.data or {}).get("status") not in ("OK", "NOTHING"):
            # PENDING (Part 1): another attempt holds this order at NuqtaPass right now. Ask again later.
            result = ApiResult(False, result.status, None, self.env._("NuqtaPass is still working on this order"),
                               "IN_PROGRESS", True)

        attempts = self.attempts + 1
        if result.ok:
            data = result.data or {}
            answer = data.get("result") if isinstance(data.get("result"), dict) else {}
            self.write({
                "state": "done",
                "attempts": attempts,
                "last_error": False,
                "last_status_code": result.status,
                "next_attempt_at": False,
                # Only what this order got or gave back: no card id, links or balances (spec: "Stored in Odoo").
                "response_json": json.dumps({
                    "status": data.get("status"),
                    "duplicate": bool(data.get("duplicate")),
                    "result": {key: answer[key] for key in RESULT_KEYS if key in answer},
                }),
            })
            return
        # Only `retryable` decides: the client already counts 401/403 (incl. "plan needed"), 429, 5xx, network,
        # CARD_FULL, IN_PROGRESS and POS_FAILED as temporary. The server's message is kept as last_error.
        delay = next_retry_delay(attempts) if result.retryable else None
        self.write({
            "attempts": attempts,
            "last_error": result.error,
            "last_status_code": result.status or 0,
            "state": "pending" if delay else "failed",
            "next_attempt_at": now + delay if delay else False,
        })

    @api.model
    def _due(self, now, limit=200):
        return self.search(
            [("state", "=", "pending"), ("next_attempt_at", "<=", now)],
            order="next_attempt_at, id", limit=limit,
        )

    @api.model
    def _send_due(self, now=None, limit=200):
        """Send what is due, without committing (used by tests)."""
        now = now or fields.Datetime.now()
        due = self._due(now, limit)
        for rec in due:
            rec._send_one(now)
        return due

    @api.model
    def _cron_send(self):
        now = fields.Datetime.now()
        due = self._due(now)
        cron = self.env["ir.cron"]
        cron._commit_progress(remaining=len(due))
        for rec in due:
            rec._send_one(now)
            if not cron._commit_progress(processed=1):
                break

    def _nuqtapass_current_phone(self):
        """The order's phone as it is now (the till and online modules read it from the order)."""
        self.ensure_one()
        return self.phone

    def action_resend(self):
        rows = self.filtered(lambda r: r.state != "done").sudo()
        for row in rows.filtered(lambda r: r.kind == "sale"):
            # Check the phone again (staff may have fixed it on the customer); a wrong one stays failed.
            phone_vals = row._sale_phone_vals(row._nuqtapass_current_phone(), row.company_id)
            if not phone_vals.get("phone") or phone_vals.get("phone_invalid"):
                row.write(row._wrong_phone_vals(phone_vals.get("phone") or row.phone))
                rows -= row
            else:
                row.write({"phone": phone_vals["phone"], "phone_invalid": False})
        rows.write({"state": "pending", "attempts": 0, "last_error": False,
                    "next_attempt_at": fields.Datetime.now()})
        cron = self.sudo().env.ref(CRON_XMLID, raise_if_not_found=False)
        if cron:
            cron._trigger()
        return True

    # ── status text ───────────────────────────────────────────────────
    @api.depends("state", "response_json", "last_error", "attempts", "kind", "phone", "phone_invalid")
    def _compute_summary(self):
        for rec in self:
            rec.summary = rec._summary_text()

    def _summary_text(self):
        _ = self.env._
        if self.state == "failed" and self.phone_invalid:
            return _("Phone number looks wrong: %(phone)s", phone=self.phone)
        if self.state == "failed":
            return _("Failed: %(error)s", error=self.last_error or _("unknown error"))
        if self.state == "pending":
            if self.last_error:
                return _("Will try again: %(error)s", error=self.last_error)
            return _("Waiting to send")
        try:
            data = json.loads(self.response_json or "{}")
        except ValueError:
            data = {}
        # Part 1 PosResult: `stamps` / `points` are what a sale gave or a refund took back; `shortfall` is what a
        # refund could not take back.
        result = data.get("result") or {}
        shortfall = result.get("shortfall") if isinstance(result.get("shortfall"), dict) else {}
        parts = []
        if self.kind == "sale":
            if result.get("stamps"):
                parts.append(_("Stamps given: %(n)s", n=result["stamps"]))
            if result.get("points"):
                parts.append(_("Points given: %(n)s", n=result["points"]))
            if not parts:
                parts.append(_("Sent, nothing to give for this card"))
        else:
            if result.get("stamps"):
                parts.append(_("Stamps taken back: %(n)s", n=result["stamps"]))
            if result.get("points"):
                parts.append(_("Points taken back: %(n)s", n=result["points"]))
            if shortfall.get("stamps"):
                parts.append(_("Stamps already used, not taken back: %(n)s", n=shortfall["stamps"]))
            if shortfall.get("points"):
                parts.append(_("Points already used, not taken back: %(n)s", n=shortfall["points"]))
            if not parts:
                parts.append(_("Sent, nothing to take back"))
        if data.get("duplicate"):
            parts.append(_("(NuqtaPass already had it)"))
        return " · ".join(str(p) for p in parts)
