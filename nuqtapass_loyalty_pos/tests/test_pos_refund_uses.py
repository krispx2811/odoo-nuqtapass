import json

from odoo.tests import tagged

from .common import PACK_CARD, POINTS_CARD, PREPAID_CARD, STAMP_CARD, VOUCHER, VOUCHER_CARD, NuqtaPassUsesCommon


@tagged("post_install", "-at_install", "nuqtapass")
class TestPosRefundUses(NuqtaPassUsesCommon):
    def _everything(self):
        """2 coffees + 1 cake (9.0); 167 points off (2.0), the cake free from a voucher, a coffee from the pack;
        0.5 left, paid with NuqtaPass credit."""
        lines = [self._line(self.coffee, 2, 2.5), self._line(self.cake, 1, 4.0), self._points_line(167, 2.0),
                 self._free_line("voucher", VOUCHER_CARD, 4.0, VOUCHER), self._free_line("pack", PACK_CARD, 2.5)]
        order = self._sync(lines, [(self.credit_pm, 0.5)])
        self._used(order, "points", POINTS_CARD, quantity=167, amount=2.0)
        self._used(order, "voucher", VOUCHER_CARD, voucher=VOUCHER)
        self._used(order, "pack", PACK_CARD)
        self._used(order, "credit", PREPAID_CARD, amount=0.5)
        return order

    def _row(self, refund):
        row = refund.nuqtapass_sync_ids
        self.assertEqual(len(row), 1)
        return row, row._payload()

    # ── earning ───────────────────────────────────────────────────────
    def test_earns_on_what_was_paid_credit_included(self):
        lines = [self._line(self.coffee, 4, 2.5), self._points_line(167, 5.01)]
        order = self._sync(lines, [(self.credit_pm, 2.5), (self.cash_pm1, 2.49)])
        sale = order.nuqtapass_sync_ids
        self.assertEqual(sale.kind, "sale")
        # The discount lowers the total; the credit payment counts as paid.
        self.assertAlmostEqual(sale.amount, 4.99)
        self.assertAlmostEqual(order.amount_total, 4.99)

    # ── refunds give back what the refunded lines used ────────────────
    def test_full_refund_gives_back_every_kind(self):
        order = self._everything()
        refund = self._refund(order, credit_back=0.5)
        row, body = self._row(refund)
        self.assertEqual(body["orderRef"], order.pos_reference)
        self.assertAlmostEqual(body["orderAmount"], order.amount_total)
        self.assertEqual(body["returnUses"], {"points": 167, "credit": 0.5, "pack": 1, "vouchers": [VOUCHER_CARD]})
        self.assertAlmostEqual(body["amount"], abs(refund.amount_total))
        self.assertEqual(json.loads(row.return_uses)["points"], 167)

    def test_products_only_refund_names_nothing(self):
        order = self._everything()
        coffee = order.lines.filtered(lambda line: line.product_id == self.coffee)
        _row, body = self._row(self._refund(order, {coffee: 1}))
        self.assertEqual(body["returnUses"], {})
        self.assertAlmostEqual(body["amount"], 2.5)

    def test_refund_of_just_the_points_line_sends_amount_zero(self):
        order = self._everything()
        points = order.lines.filtered(lambda line: line.nuqtapass_use == "points")
        _row, body = self._row(self._refund(order, {points: 1}))
        self.assertEqual((body["amount"], body["returnUses"]), (0, {"points": 167}))

    def test_reward_line_refund_gives_the_reward_back(self):
        lines = [self._line(self.coffee, 1, 2.5), self._free_line("reward", STAMP_CARD, 2.5),
                 self._line(self.cake, 1, 4.0)]
        order = self._sync(lines, [(self.cash_pm1, 4.0)])
        self._used(order, "reward", STAMP_CARD)
        _row, body = self._row(self._refund(order))
        self.assertEqual(body["returnUses"], {"reward": True})

    def test_order_that_used_but_never_earned_still_refunds(self):
        # No sale row (NuqtaPass earns nothing, e.g. the till switched off after Validate): the uses still come back.
        order = self._everything()
        order.nuqtapass_sync_ids.unlink()
        _row, body = self._row(self._refund(order, credit_back=0.5))
        self.assertEqual(body["returnUses"]["points"], 167)
        self.assertEqual(_row.phone, "+96891234567")

    def test_plain_refund_sends_order_amount_and_empty_uses(self):
        order = self._sync([self._line(self.coffee, 2, 2.5)], [(self.cash_pm1, 5.0)])
        _row, body = self._row(self._refund(order))
        self.assertEqual((body["orderAmount"], body["returnUses"]), (5.0, {}))
