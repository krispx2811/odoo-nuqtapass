import { _t } from "@web/core/l10n/translation";
import { fitPoints, formatNumber } from "./nuqtapass_math";
import { exactPointsTotal, pointsUse, splitPointsByTax } from "./points_tax";

// The order's NuqtaPass lines and payment. Adding them spends nothing: Validate does (pay_validation.js).
//  - points:  "NuqtaPass points", −value split over the order's tax groups (one line per group, with its taxes, as
//             Odoo's own discounts: VAT is charged on the discounted price), the points in the note; pressing again
//             replaces them
//  - pack / reward / voucher: one unit of the item it covers made free (−its unit price, with its own taxes and
//    discount, so the item nets to exactly 0)
//  - credit:  a "NuqtaPass credit" payment line, one per order

export function rewardProduct(pos) {
    return pos.config.nuqtapass_reward_product_id || null;
}

/** Why a NuqtaPass line can't go on the order: the till loaded without NuqtaPass's product (or credit method). */
export function cantAddLine() {
    return _t("This till isn't ready for NuqtaPass yet. Reload the till page, then try again.");
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

/** The order's points lines (one per tax group). */
export function pointsLines(order) {
    return order.lines.filter((line) => line.nuqtapass_use === "points");
}

/** The order's total before its NuqtaPass points lines (below 0 when free items cover more than is on it). */
function rawTotalWithoutPoints(order) {
    const off = pointsLines(order).reduce((sum, line) => sum + line.priceIncl, 0);
    return order.priceIncl - off;
}

/** The order's total before its NuqtaPass points lines: what the points can take off at most. */
export function totalWithoutPoints(order) {
    return Math.max(0, rawTotalWithoutPoints(order));
}

/** Half the till currency's smallest unit: totals closer to 0 than this are 0. */
function halfUnit(pos) {
    return 10 ** -(pos.currency?.decimal_places ?? 3) / 2;
}

/** Whether the order's total is below 0 (free items or points taking off more than is on it). */
export function belowZero(pos, order) {
    return order.priceIncl < -halfUnit(pos);
}

/** Whether making one unit of `covered` free (replacing the order's earlier line for this use) keeps the order's
 * total before points at 0 or more: a second free line on the same item would not. */
export function freeLineFits(pos, order, use, covered, cardId = null) {
    const unit = covered.qty ? covered.priceIncl / covered.qty : 0;
    const earlier = lineFor(order, use, use === "voucher" ? cardId : null);
    const after = rawTotalWithoutPoints(order) - unit - (earlier ? earlier.priceIncl : 0);
    return after >= -halfUnit(pos);
}

/**
 * After a free item lowered the order's total: fewer points (or none) when their value is now more than the total
 * without them, so the order never goes below 0. Answers the new { points, value }, or null when nothing changed.
 */
export async function fitPointsLine(pos, order, card, decimals) {
    const lines = pointsLines(order);
    if (!lines.length) {
        return null;
    }
    const points = lines.reduce((sum, line) => sum + (line.nuqtapass_qty || 0), 0);
    const value = lines.reduce((sum, line) => sum + Math.abs(line.priceIncl), 0);
    const plan = fitPoints({ points, value, ppu: card?.pointsPerUnit, decimals, maxValue: totalWithoutPoints(order) });
    if (plan.points === points) {
        return null;
    }
    if (plan.points > 0) {
        await setPointsLine(pos, order, card, plan);
    } else {
        lines.forEach((line) => order.removeOrderline(line));
    }
    return plan;
}

/** The lines the points are weighed over: the order's own lines (free-item lines too), not tips or combo parents. */
function taxedLines(order) {
    return order.lines
        .filter(
            (line) =>
                line.nuqtapass_use !== "points" &&
                line.qty &&
                !line.combo_line_ids?.length &&
                !line.isTipLine?.()
        )
        .map((line) => ({ taxes: line.tax_ids || [], included: line.priceIncl, excluded: line.priceExcl }));
}

export function pointsNote(points) {
    const n = formatNumber(points);
    return points === 1 ? _t("1 point used") : _t("%(points)s points used", { points: n });
}

/** Put the order's points lines, one per tax group (replacing those there). Answers the lines added. */
export async function setPointsLine(pos, order, card, { points, value }) {
    const product = rewardProduct(pos);
    if (!product) {
        return [];
    }
    for (const old of pointsLines(order)) {
        old.delete();
    }
    const decimals = pos.currency?.decimal_places ?? 3; // the line is in the till's currency
    const before = order.priceIncl;
    const added = [];
    for (const part of splitPointsByTax(taxedLines(order), { value, points, decimals })) {
        const line = await pos.addLineToOrder(
            {
                product_id: product,
                product_tmpl_id: product.product_tmpl_id,
                price_unit: part.priceUnit,
                qty: 1,
                tax_ids: part.taxes.map((tax) => ["link", tax]),
                nuqtapass_use: "points",
                nuqtapass_card_id: card.cardId,
                nuqtapass_qty: part.points,
                nuqtapass_label: _t("NuqtaPass points"),
            },
            order,
            { force: true },
            false
        );
        if (line) {
            line.setCustomerNote(pointsNote(part.points));
            added.push(line);
        }
    }
    exactPointsTotal(order, added.at(-1), before - value, decimals);
    return added;
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
    const points = pointsUse(pointsLines(order));
    const uses = points ? [points] : [];
    for (const line of nuqtapassLines(order)) {
        const base = { use: line.nuqtapass_use, card_id: line.nuqtapass_card_id, label: line.nuqtapass_label || line.full_product_name };
        if (line.nuqtapass_use === "points") {
            continue; // one use for all of them, above
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
