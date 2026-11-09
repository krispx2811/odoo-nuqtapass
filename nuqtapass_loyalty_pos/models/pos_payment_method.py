import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)
JOURNAL_CODE = "NPCR"
NAME = "NuqtaPass credit"
ARABIC_NAME = "رصيد نقطة باس"


class PosPaymentMethod(models.Model):
    _inherit = "pos.payment.method"

    nuqtapass_credit = fields.Boolean(
        "NuqtaPass credit", copy=False,
        help="The customer pays with prepaid credit bought at NuqtaPass. It shows with the till's other methods, "
             "but adds a payment only for a looked-up customer's credit card (as the NuqtaPass panel does), and "
             "NuqtaPass takes the amount off the card when the order is validated.")

    @api.model
    def _load_pos_data_fields(self, config):
        return super()._load_pos_data_fields(config) + ["nuqtapass_credit"]

    @api.model
    def _nuqtapass_credit_method(self, company):
        """The company's "NuqtaPass credit" method, made once and put on all its tills.

        The credit was paid for when the customer bought it at NuqtaPass, so here it is a payment (not a discount).
        It is a bank method on its own journal; its outstanding account is a current liability, "NuqtaPass prepaid
        credit": at session close a use settles that liability, as an Odoo gift card does, and the sale's revenue and
        tax are booked as usual. The accountant credits the liability when credit is sold.
        """
        method = self.sudo().with_company(company).search(
            [("nuqtapass_credit", "=", True), ("company_id", "=", company.id)], limit=1)
        if not method:
            env = self.sudo().with_company(company).env
            journal = env["account.journal"].search(
                [("code", "=", JOURNAL_CODE), ("company_id", "=", company.id)], limit=1) or env["account.journal"].create(
                {"name": env._("NuqtaPass credit"), "code": JOURNAL_CODE, "type": "bank", "company_id": company.id})
            # In English, with the Arabic as its translation (the till shows the cashier's language).
            method = env["pos.payment.method"].with_context(lang="en_US").create({
                "name": NAME,
                "type": "bank",
                "journal_id": journal.id,
                "company_id": company.id,
                "nuqtapass_credit": True,
                "outstanding_account_id": self._nuqtapass_liability_account(company).id,
            }).with_env(env)
            method._nuqtapass_arabic_name()
        configs = self.env["pos.config"].sudo().search(
            [("company_id", "=", company.id), ("payment_method_ids", "not in", method.ids)])
        if configs:
            # Also a till with its session open (left open across the upgrade): adding a method is safe, and Odoo 19
            # refuses any change to the methods then unless told to let it through.
            configs.with_context(bypass_payment_method_ids_forbidden_change=True).write(
                {"payment_method_ids": [(4, method.id)]})
        return method

    def _nuqtapass_arabic_name(self):
        """The method's name in the till's Arabic: "رصيد نقطة باس", unless the shop renamed it. Also with a till's
        session open (only the name's translation changes). Never raises."""
        langs = [code for code, _name in self.env["res.lang"].get_installed() if code.startswith("ar")]
        for method in self.sudo().with_context(nuqtapass_name_only=True):
            if not langs or method.with_context(lang="en_US").name != NAME:
                continue
            if all(method.with_context(lang=lang).name == ARABIC_NAME for lang in langs):
                continue
            try:
                with self.env.cr.savepoint():
                    method.update_field_translations("name", dict.fromkeys(langs, ARABIC_NAME))
            except Exception:
                _logger.exception("NuqtaPass: could not name the NuqtaPass credit method in Arabic")

    def _is_write_forbidden(self, fields):
        # Odoo refuses changing a method of an open session; its name's translation is harmless.
        if self.env.context.get("nuqtapass_name_only") and set(fields) <= {"name"} and all(
                self.mapped("nuqtapass_credit")):
            return False
        return super()._is_write_forbidden(fields)

    @api.model
    def _nuqtapass_liability_account(self, company):
        Account = self.env["account.account"].sudo().with_company(company)
        name = self.env._("NuqtaPass prepaid credit")
        account = Account.search([("name", "=", name), ("account_type", "=", "liability_current"),
                                  ("company_ids", "in", company.id)], limit=1)
        if account:
            return account
        start = Account.search([("account_type", "=", "liability_current"), ("company_ids", "in", company.id)],
                               order="code desc", limit=1).code or "2999"
        return Account.create({
            "name": name, "code": Account._search_new_account_code(start), "account_type": "liability_current",
            "company_ids": [(6, 0, company.ids)], "reconcile": True,
        })

    @api.model
    def _nuqtapass_ensure_all(self):
        """For every company with a till (module install, the till switch turned on)."""
        for company in self.env["pos.config"].sudo().search([]).company_id:
            try:
                with self.env.cr.savepoint():
                    method = self._nuqtapass_credit_method(company)
            except Exception:  # a company without accounting set up: the till works without NuqtaPass credit
                _logger.exception("NuqtaPass: could not add the NuqtaPass credit method for company %s", company.id)
                continue
            method._nuqtapass_arabic_name()
