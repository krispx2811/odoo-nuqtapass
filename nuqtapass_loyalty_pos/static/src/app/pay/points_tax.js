// The NuqtaPass points line split by the order's taxes, the way Odoo's own pos_loyalty discount lines are
// (20.0 loyalty_reward.js getRewardLines, 19.0 pos_order.js _getRewardLineValuesDiscount): the order's lines are
// grouped by their taxes (fixed-amount taxes left out), and each group gets one negative line with those taxes,
// worth its tax-included share of the points' value. So the discount lowers the taxable amount and VAT is charged
// on the discounted price. Plain JS (no Odoo imports): tests/js/points_tax.test.mjs.

const round = (n, decimals) => {
    const f = 10 ** decimals;
    return Math.round((n + Number.EPSILON * Math.sign(n)) * f) / f;
};

/**
 * @param {{taxes: object[], included: number, excluded: number}[]} lines the order's lines, without its points lines
 * @param {{value: number, points: number, decimals: number}} use the points' value (tax included), their count
 * @returns {{taxes: object[], priceUnit: number, points: number}[]} one line per tax group, in the order's order;
 *   `priceUnit` is before tax unless a group tax is price-included (then with it, as Odoo prices those lines)
 */
export function splitPointsByTax(lines, { value, points, decimals }) {
    const groups = new Map();
    for (const line of lines) {
        const taxes = (line.taxes || []).filter((tax) => tax.amount_type !== "fixed");
        const key = taxes
            .map((tax) => tax.id)
            .sort((a, b) => a - b)
            .join(",");
        if (!groups.has(key)) {
            groups.set(key, { taxes, included: 0, excluded: 0 });
        }
        const group = groups.get(key);
        group.included += line.included;
        group.excluded += line.excluded;
    }
    const kept = [...groups.values()].filter((group) => group.included > 1e-9);
    const total = kept.reduce((sum, group) => sum + group.included, 0);
    if (!kept.length || total <= 0) {
        return [{ taxes: [], priceUnit: round(-value, decimals), points }];
    }
    const factor = Math.min(1, value / total);
    // Whole points per line, in proportion to the group's share; the points left over go to the largest remainders.
    const shares = kept.map((group) => (points * group.included) / total);
    const counts = shares.map((share) => Math.floor(share + 1e-9));
    let left = points - counts.reduce((sum, n) => sum + n, 0);
    const byRemainder = shares.map((share, i) => [share - counts[i], i]).sort((a, b) => b[0] - a[0]);
    for (let k = 0; left > 0; k = (k + 1) % byRemainder.length, left--) {
        counts[byRemainder[k][1]] += 1;
    }
    return kept.map((group, i) => {
        const base = group.taxes.some((tax) => tax.price_include) ? group.included : group.excluded;
        return { taxes: group.taxes, priceUnit: round(-(base * factor), decimals) || 0, points: counts[i] };
    });
}

/** The order's points lines as Validate's one points use: their points summed, the first line's ref, or null. */
export function pointsUse(lines) {
    if (!lines.length) {
        return null;
    }
    const first = lines[0];
    return {
        use: "points",
        card_id: first.nuqtapass_card_id,
        label: first.nuqtapass_label || first.full_product_name,
        points: lines.reduce((sum, line) => sum + (line.nuqtapass_qty || 0), 0),
        ref: first.uuid,
    };
}

/**
 * Each points line is priced before tax and rounded, so together they can take off a little more or less than the
 * points' value (28.130 off for 28.160). The last line takes the difference, so the order comes to exactly
 * `target` (0.000 when the points cover it all).
 */
export function exactPointsTotal(order, last, target, decimals) {
    const unit = 10 ** -decimals;
    const round = (n) => Math.round(n / unit) * unit;
    for (let tries = 0; last && tries < 6; tries++) {
        const diff = round(target - order.priceIncl);
        if (Math.abs(diff) < unit / 2) {
            return;
        }
        // The line's price before tax moves by its own tax-included / tax-excluded ratio.
        const ratio = last.priceIncl && last.priceExcl ? last.priceExcl / last.priceIncl : 1;
        let step = round(diff * ratio);
        if (Math.abs(step) < unit / 2) {
            step = Math.sign(diff) * unit;
        }
        last.setUnitPrice(round(last.price_unit + step));
    }
}
