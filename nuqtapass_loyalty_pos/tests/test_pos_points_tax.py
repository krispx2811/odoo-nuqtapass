import json
from random import randint

from odoo.tests import tagged

from .common import POINTS_CARD, NuqtaPassUsesCommon


@tagged("post_install", "-at_install", "nuqtapass")
class TestPosPointsTax(NuqtaPassUsesCommon):
    """The NuqtaPass points line lowers the taxable amount like Odoo's own discounts: the till splits it per tax group
    (static/src/app/pay/points_tax.js), so each part carries its group's taxes and VAT is charged on the discounted
    price. Here: the lines the till sends for a 5 % cake (4.000 + 0.200 VAT) and an untaxed coffee (2.500), with 111
    points worth 3.350 off (half the order)."""

    def setUp(self):
        super().setUp()
        self.vat5 = self.env["account.tax"].create({
            "name": "VAT 5%", "amount": 5, "amount_type": "percent", "price_include_override": "tax_excluded",
            "type_tax_use": "sale", "company_id": self.env.company.id})
        self.taxed_cake = self.create_product("Taxed cake", self.categ_basic, 4.0, 1.0, tax_ids=self.vat5.ids)

    def _taxed(self, product, qty, price_unit, taxes, **extra):
        excluded = price_unit * qty
        included = excluded * (1 + sum(taxes.mapped("amount")) / 100)
        return (0, 0, {"id": randint(1, 1000000), "product_id": product.id, "qty": qty, "price_unit": price_unit,
                       "price_subtotal": abs(excluded), "price_subtotal_incl": abs(included),
                       "tax_ids": [(6, 0, taxes.ids)], **extra})

    def _order(self, split=True):
        no_tax = self.env["account.tax"]
        points = {"nuqtapass_use": "points", "nuqtapass_card_id": POINTS_CARD, "full_product_name": "NuqtaPass points"}
        if split:  # what the till sends now: −2.000 at 5 % (70 points) and −1.250 untaxed (41 points)
            off = [self._taxed(self.reward, 1, -2.0, self.vat5, nuqtapass_qty=70, **points),
                   self._taxed(self.reward, 1, -1.25, no_tax, nuqtapass_qty=41, **points)]
        else:  # before: one untaxed line
            off = [self._taxed(self.reward, 1, -3.35, no_tax, nuqtapass_qty=111, **points)]
        lines = [self._taxed(self.taxed_cake, 1, 4.0, self.vat5), self._taxed(self.coffee, 1, 2.5, no_tax)] + off
        order = self._sync(lines, [(self.cash_pm1, 3.35)])
        order._compute_prices()  # Odoo's own tax engine over the stored lines
        return order

    def test_vat_is_charged_on_the_discounted_price(self):
        order = self._order()
        # 5 % of the 2.000 left of the cake, not of its 4.000.
        self.assertAlmostEqual(order.amount_tax, 0.1)
        self.assertAlmostEqual(order.amount_total, 3.35)

    def test_an_untaxed_points_line_left_the_full_vat(self):
        # The review's bug, kept as the contrast: the old single untaxed line charged VAT on the full 4.000.
        self.assertAlmostEqual(self._order(split=False).amount_tax, 0.2)

    def test_the_invoice_charges_vat_on_the_discounted_price(self):
        order = self._order()
        order.partner_id = self.customer
        order.action_pos_order_invoice()
        self.assertAlmostEqual(order.account_move.amount_tax, 0.1)
        self.assertAlmostEqual(order.account_move.amount_total, 3.35)

    def test_refund_gives_back_the_points_of_every_part(self):
        order = self._order()
        self._used(order, "points", POINTS_CARD, quantity=111, amount=3.35)
        refund = self._refund(order)
        returned = json.loads(refund.nuqtapass_sync_ids.return_uses)
        self.assertEqual(returned["points"], 111)
