import json
import logging
from datetime import timezone

from odoo import api, fields, models

from odoo.addons.nuqtapass_loyalty.lib.client import DEFAULT_BASE_URL, NuqtaPassClient
from odoo.addons.nuqtapass_loyalty.lib.phone import normalise_e164

_logger = logging.getLogger(__name__)

PARAM_KEY = "nuqtapass_loyalty.api_key"
PARAM_BASE_URL = "nuqtapass_loyalty.base_url"
CRON_XMLID = "nuqtapass_loyalty.ir_cron_nuqtapass_send"


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
        return normalise_e164(raw, company.country_id.phone_code or None)

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

    @api.depends("state")
    def _compute_summary(self):
        for rec in self:
            rec.summary = False  # replaced in Task 8
