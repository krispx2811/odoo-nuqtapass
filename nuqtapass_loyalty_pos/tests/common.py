from random import randint

from odoo.addons.nuqtapass_loyalty.lib.client import ApiResult
from odoo.addons.point_of_sale.tests.common import TestPoSCommon

PHONE = "+96891234567"
POINTS_CARD = "aaaaaaaa-2222-4222-8222-222222222222"
PREPAID_CARD = "bbbbbbbb-2222-4222-8222-222222222222"
PACK_CARD = "cccccccc-2222-4222-8222-222222222222"
STAMP_CARD = "cccccccc-1111-4111-8111-111111111111"
VOUCHER_CARD = "dddddddd-1111-4111-8111-111111111111"
VOUCHER = "eeeeeeee-1111-4111-8111-111111111111"


def ok(data, status=200):
    return ApiResult(True, status, data, None, None, False)


def refused(error, code=None, status=400):
    return ApiResult(False, status, None, error, code, False)


DOWN = ApiResult(False, None, None, "Could not reach NuqtaPass (ConnectionError)", "NETWORK", True)


class NuqtaPassUsesCommon(TestPoSCommon):
    """A till with NuqtaPass on, a coffee, and helpers for orders that used NuqtaPass at payment."""

    def setUp(self):
        super().setUp()
        self.config = self.basic_config
        self.env.company.country_id = self.env.ref("base.om")
        icp = self.env["ir.config_parameter"].sudo()
        icp.set_param("nuqtapass_loyalty.till_enabled", "True")
        icp.set_param("nuqtapass_loyalty.api_key", "sip_test")
        self.coffee = self.create_product("Coffee", self.categ_basic, 2.5, 1.0)
        self.cake = self.create_product("Cake", self.categ_basic, 4.0, 1.0)
        self.customer.phone = "9123 4567"
        self.Sync = self.env["nuqtapass.sync"].sudo()
        self.Use = self.env["nuqtapass.pos.use"].sudo()
        self.credit_pm = self.env["pos.payment.method"]._nuqtapass_credit_method(self.env.company)
        self.reward = self.env["pos.config"]._nuqtapass_reward_product()
        self.open_new_session()

    def _line(self, product, qty, price_unit, **extra):
        total = price_unit * qty
        return (0, 0, {
            "id": randint(1, 1000000), "product_id": product.id, "qty": qty, "price_unit": price_unit,
            "price_subtotal": abs(total), "price_subtotal_incl": abs(total), "tax_ids": [(6, 0, [])], **extra,
        })

    def _points_line(self, points, value):
        return self._line(self.reward, 1, -value, nuqtapass_use="points", nuqtapass_card_id=POINTS_CARD,
                          nuqtapass_qty=points, full_product_name="NuqtaPass points")

    def _free_line(self, use, card, price, voucher=None):
        return self._line(self.reward, 1, -price, nuqtapass_use=use, nuqtapass_card_id=card,
                          nuqtapass_voucher_id=voucher or False, nuqtapass_qty=1)

    def _sync(self, lines, payments, phone=PHONE, ref=None):
        """A paid till order with these line tuples and (method, amount) payments."""
        data = self.create_ui_order_data([], {"nuqtapass_phone": phone}, payments=payments)
        data["lines"] = lines
        total = sum(line[2]["price_unit"] * line[2]["qty"] for line in lines)
        data.update(amount_total=total, amount_tax=0, amount_paid=sum(a for _pm, a in payments))
        if ref:
            data["pos_reference"] = ref
        res = self.env["pos.order"].sync_from_ui([data])
        return self.env["pos.order"].browse(res["pos.order"][0]["id"])

    def _used(self, order, use, card, quantity=1, amount=0.0, voucher=False):
        """What the till's Validate recorded for this order at NuqtaPass (the spend route writes these)."""
        return self.Use.create({
            "company_id": self.env.company.id, "config_id": self.config.id, "order_ref": order.pos_reference,
            "phone": PHONE, "use": use, "card_id": card, "voucher_id": voucher, "quantity": quantity,
            "amount": amount, "transaction_id": "t-" + use,
        })

    def _refund(self, order, lines_qty=None, credit_back=0.0):
        """Refund `order` in the back office: every line, or {line: qty} for some; give back `credit_back` as
        NuqtaPass credit and the rest in cash."""
        refund = self.env["pos.order"].browse(order.refund()["res_id"])
        if lines_qty is not None:
            for line in refund.lines:
                qty = lines_qty.get(line.refunded_orderline_id, 0)
                if qty:
                    line.qty = -qty
                else:
                    line.unlink()
            refund.lines._onchange_amount_line_all()
            refund._compute_prices()
        if credit_back:
            self.make_payment(refund, self.credit_pm, -credit_back)
        rest = refund.amount_total - refund.amount_paid
        if not refund.currency_id.is_zero(rest) or not refund.payment_ids:
            self.make_payment(refund, self.cash_pm1, rest)
        return refund
