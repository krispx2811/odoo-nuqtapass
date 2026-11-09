import { _t } from "@web/core/l10n/translation";
import { formatNumber } from "./nuqtapass_math";

// The order's NuqtaPass lines and payment. Adding them spends nothing: Validate does (pay_validation.js).
//  - points:  "NuqtaPass points", −value, no tax, the points in its note; one per order (pressing again replaces it)
//  - pack / reward / voucher: one unit of the item it covers made free (−its unit price, with its own taxes and
//    discount, so the item nets to exactly 0)
//  - credit:  a "NuqtaPass credit" payment line, one per order

export function rewardProduct(pos) {
    return pos.config.nuqtapass_reward_product_id || null;
}

export function creditMethod(pos) {
    return pos.config.payment_method_ids.find((pm) => pm.nuqtapass_credit) || null;
}

export function nuqtapassLines(order) {
    return order.lines.filter((line) => line.nuqtapass_use);
}

export function lineFor(order, use, cardId = null) {
    return nuqtapassLines(order).find(
        (line) => line.nuqtapass_use === use && (!cardId || line.nuqtapass_card_id === cardId)
    );
}

export function creditPayment(order) {
    return order.payment_ids.find((p) => p.payment_method_id?.nuqtapass_credit);
}

/** The lines a pack use or a reward can make free: the order's own product lines, one row per line. */
export function coverableLines(order) {
    return order.lines.filter((line) => !line.nuqtapass_use && line.qty > 0 && line.price_unit > 0);
}

/** The order's total before its NuqtaPass points line: what the points can take off at most. */
export function totalWithoutPoints(order) {
    const line = lineFor(order, "points");
    return Math.max(0, order.priceIncl - (line ? line.priceIncl : 0));
}

export function pointsNote(points) {
    const n = formatNumber(points);
    return points === 1 ? _t("1 point used") : _t("%(points)s points used", { points: n });
}

/** Put the order's points line (replacing the one there). */
export async function setPointsLine(pos, order, card, { points, value }) {
    const product = rewardProduct(pos);
    if (!product) {
        return null;
    }
    lineFor(order, "points")?.delete();
    const line = await pos.addLineToOrder(
        {
            product_id: product,
            product_tmpl_id: product.product_tmpl_id,
            price_unit: -value,
            qty: 1,
            tax_ids: [],
            nuqtapass_use: "points",
            nuqtapass_card_id: card.cardId,
            nuqtapass_qty: points,
            nuqtapass_label: _t("NuqtaPass points"),
        },
        order,
        { force: true },
        false
    );
    line?.setCustomerNote(pointsNote(points));
    return line;
}

/** Make one unit of `covered` free with a pack use, a stamp reward or a voucher (replacing the earlier one). */
export async function setFreeLine(pos, order, card, use, covered) {
    const product = rewardProduct(pos);
    if (!product || !covered) {
        return null;
    }
    const cardId = use === "voucher" ? card.cardId : null;
    lineFor(order, use, cardId)?.delete();
    const item = covered.getFullProductName ? covered.getFullProductName() : covered.full_product_name;
    const line = await pos.addLineToOrder(
        {
            product_id: product,
            product_tmpl_id: product.product_tmpl_id,
            price_unit: -covered.price_unit,
            discount: covered.discount || 0,
            qty: 1,
            tax_ids: covered.tax_ids.map((tax) => ["link", tax]),
            nuqtapass_use: use,
            nuqtapass_card_id: card.cardId,
            nuqtapass_voucher_id: use === "voucher" ? card.voucher?.id || false : false,
            nuqtapass_qty: 1,
            nuqtapass_label: use === "pack" ? _t("Service pack (1 use)") : _t("Reward: free %(item)s", { item }),
        },
        order,
        { force: true },
        false
    );
    line?.setCustomerNote(use === "pack" ? item : use === "voucher" ? card.voucher?.title || "" : "");
    return line;
}

/** Pay `amount` with NuqtaPass credit (replacing the order's earlier credit line). */
export function setCreditPayment(pos, order, card, amount) {
    const method = creditMethod(pos);
    if (!method) {
        return null;
    }
    const existing = creditPayment(order);
    if (existing) {
        order.removePaymentline(existing);
    }
    const result = order.addPaymentline(method);
    if (!result.status) {
        return null;
    }
    result.data.setAmount(amount);
    result.data.nuqtapass_card_id = card.cardId;
    return result.data;
}

export function removeAllNuqtaPass(order) {
    for (const line of nuqtapassLines(order)) {
        order.removeOrderline(line);
    }
    const credit = creditPayment(order);
    if (credit) {
        order.removePaymentline(credit);
    }
}

/** What Validate sends to the spend route, with each line's name for a refusal. */
export function orderUses(order) {
    const uses = [];
    for (const line of nuqtapassLines(order)) {
        const base = { use: line.nuqtapass_use, card_id: line.nuqtapass_card_id, label: line.nuqtapass_label || line.full_product_name };
        if (line.nuqtapass_use === "points") {
            uses.push({ ...base, points: line.nuqtapass_qty, ref: line.uuid });
        } else if (line.nuqtapass_use === "pack") {
            uses.push({ ...base, uses: 1, ref: line.uuid });
        } else if (line.nuqtapass_use === "voucher") {
            uses.push({ ...base, voucher_id: line.nuqtapass_voucher_id || null, ref: line.uuid });
        } else {
            uses.push({ ...base, ref: line.uuid });
        }
    }
    const credit = creditPayment(order);
    const creditCard = credit?.nuqtapass_card_id;
    if (credit && creditCard && credit.getAmount() > 0) {
        uses.push({
            use: "credit",
            card_id: creditCard,
            amount: credit.getAmount(),
            label: credit.payment_method_id.name,
            ref: credit.uuid,
            payment: true,
        });
    }
    return uses;
}
