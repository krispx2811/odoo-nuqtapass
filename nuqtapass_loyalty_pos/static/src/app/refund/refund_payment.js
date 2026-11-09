import { patch } from "@web/core/utils/patch";
import { TicketScreen } from "@point_of_sale/app/screens/ticket_screen/ticket_screen";
import { refundSplit } from "../pay/nuqtapass_math";
import { creditMethod } from "../pay/nuqtapass_lines";

/** The order's payments' total with `test` (NuqtaPass credit or not). */
function paid(order, test) {
    return (order.payment_ids || [])
        .filter((p) => Boolean(p.payment_method_id?.nuqtapass_credit) === test)
        .reduce((sum, p) => sum + (p.amount || 0), 0);
}

/** The order's main other method (its biggest non-credit payment) when this till has it, else the till's first. */
function otherMethod(pos, order) {
    const onTill = pos.config.payment_method_ids.filter((pm) => !pm.nuqtapass_credit);
    const biggest = (order.payment_ids || [])
        .filter((p) => p.payment_method_id && !p.payment_method_id.nuqtapass_credit && p.amount > 0)
        .sort((a, b) => b.amount - a.amount)
        .map((p) => onTill.find((pm) => pm.id === p.payment_method_id.id))
        .find(Boolean);
    return biggest || onTill[0] || null;
}

patch(TicketScreen.prototype, {
    /** A refund of an order paid partly with NuqtaPass credit: its payment screen starts with the split of the
     * original (the refund's share of the credit back as credit, the rest the order's other way). Staff can change
     * it; what is paid back as credit is what NuqtaPass gives back (returnUses). */
    postRefund(destinationOrder) {
        super.postRefund(...arguments);
        try {
            this.nuqtapassPrefillRefund(destinationOrder);
        } catch {
            // Never in the way of a refund: staff then pick the methods themselves.
        }
    },

    nuqtapassPrefillRefund(refund) {
        const original = refund.refunded_order_id;
        const credit = creditMethod(this.pos);
        if (!original || !credit || refund.payment_ids.length) {
            return;
        }
        const creditPaid = paid(original, true);
        if (!(creditPaid > 0)) {
            return;
        }
        const decimals = this.pos.currency.decimal_places;
        const split = refundSplit({
            refundTotal: -refund.priceIncl,
            orderTotal: original.amount_total,
            creditPaid,
            decimals,
        });
        if (!(split.credit > 0)) {
            return;
        }
        const pay = (method, amount) => {
            const added = refund.addPaymentline(method);
            if (added.status) {
                added.data.setAmount(-amount);
            }
        };
        pay(credit, split.credit);
        const other = split.rest > 0 ? otherMethod(this.pos, original) : null;
        if (other) {
            pay(other, split.rest);
        }
    },
});
