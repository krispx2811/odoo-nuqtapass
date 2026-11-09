// The till's NuqtaPass money math. Plain functions with no imports, so tests/js runs them with `node --test`.
//
// Every NuqtaPass amount on the till is in the shop's NuqtaPass currency ({code, symbol, decimals} from /customer),
// never the till's own currency: a shop's Odoo may be set up in another currency than its NuqtaPass shop.

const EPS = 1e-9;

// Gulf currencies in Arabic: their plain-text abbreviations (no currency glyph); the code for every other.
const ARABIC_SYMBOLS = {
    OMR: "ر.ع.",
    AED: "د.إ",
    SAR: "ر.س",
    KWD: "د.ك",
    BHD: "د.ب",
    QAR: "ر.ق",
};

function roundTo(value, decimals) {
    const f = 10 ** decimals;
    return Math.round((value + Math.sign(value) * EPS) * f) / f;
}

function floorTo(value, decimals) {
    const f = 10 ** decimals;
    return Math.floor(value * f + EPS) / f;
}

const usable = (n) => typeof n === "number" && Number.isFinite(n) && n > 0;

/** Whole points for `amount` of money: always rounded down, so their value is never more than the amount. */
export function pointsFor(amount, pointsPerUnit) {
    if (!usable(amount) || !usable(pointsPerUnit)) {
        return 0;
    }
    // The rate comes rounded (1 point = 0.030 is 33.333333 points per unit): 10.5 is 349.99999 of them, so 350.
    return Math.floor(amount * pointsPerUnit + 1e-4);
}

/** The money value of whole points, rounded to the currency's decimals. */
export function valueOfPoints(points, pointsPerUnit, decimals) {
    if (!usable(points) || !usable(pointsPerUnit)) {
        return 0;
    }
    return roundTo(points / pointsPerUnit, decimals);
}

/**
 * The points line for a typed amount.
 *  - points = floor(amount × points per unit), so the discount (the value of those whole points) is never more than
 *    was typed, the card has, the shop's per-visit cap allows or `maxValue` (the order's total before points);
 *  - but when that would leave less than one point's worth to pay (23.540 off a 23.560 order at 0.030 a point), one
 *    more point covers the order and the discount is exactly `maxValue`, so it comes to 0: when the card and the
 *    per-visit cap allow that many points.
 * `capped` says what held the typed amount back: {reason: "due" | "card" | "cap", value} (in money), or null.
 */
export function planPoints({ amount, ppu, decimals, cardPoints, capPoints = null, maxValue = Infinity }) {
    const none = { points: 0, value: 0, capped: null };
    if (!usable(amount) || !usable(ppu)) {
        return none;
    }
    const half = 10 ** -decimals / 2;
    const card = Math.max(0, Math.floor(cardPoints || 0));
    const cap = capPoints !== null && capPoints !== undefined ? Math.max(0, capPoints) : Infinity;
    let points = pointsFor(amount, ppu);
    let capped = null;
    if (points > card) {
        points = card;
        capped = { reason: "card", value: valueOfPoints(card, ppu, decimals) };
    }
    if (points > cap) {
        points = cap;
        capped = { reason: "cap", value: valueOfPoints(cap, ppu, decimals) };
    }
    const most = Math.min(maxValue, amount);
    while (points > 0 && valueOfPoints(points, ppu, decimals) > most + EPS) {
        points -= 1;
    }
    if (Number.isFinite(maxValue) && maxValue > 0) {
        const left = maxValue - (points > 0 ? valueOfPoints(points, ppu, decimals) : 0);
        const cover = Math.ceil(maxValue * ppu - 1e-4);
        if (left > half && left < 1 / ppu + EPS && cover <= card && cover <= cap) {
            const value = roundTo(maxValue, decimals);
            return { points: cover, value, capped: amount > maxValue + half ? { reason: "due", value } : null };
        }
        if (amount > maxValue + half && !capped) {
            capped = { reason: "due", value: roundTo(maxValue, decimals) };
        }
    }
    return points > 0 ? { points, value: valueOfPoints(points, ppu, decimals), capped } : none;
}

/**
 * The order's points after something else lowered its total (a free item): the same points while their value still
 * fits in `maxValue` (the order's total without them), else fewer, so the order never goes below 0.
 */
export function fitPoints({ points, value, ppu, decimals, maxValue }) {
    if (!(points > 0) || value <= maxValue + EPS) {
        return { points, value };
    }
    const plan = planPoints({ amount: Math.max(0, maxValue), ppu, decimals, cardPoints: points, maxValue });
    return { points: plan.points, value: plan.value };
}

/** The money box's first value: the smallest of the order's total, the card's worth and the per-visit cap. */
export function startingAmount({ orderTotal, cardWorth, capValue = null, decimals }) {
    const limits = [orderTotal, cardWorth].concat(capValue === null || capValue === undefined ? [] : [capValue]);
    const smallest = Math.min(...limits.map((n) => (Number.isFinite(n) ? n : 0)));
    return smallest > 0 ? floorTo(smallest, decimals) : 0;
}

/** Prepaid credit to use: what was typed, no more than the balance or what is still due. */
export function creditAmount({ amount, balance, due, decimals }) {
    if (!usable(amount)) {
        return 0;
    }
    return floorTo(Math.max(0, Math.min(amount, balance || 0, due || 0)), decimals);
}

/** "1,404": Latin digits, comma thousands (the same in the Arabic till, as on the customer's card). */
export function formatNumber(n, decimals = 0) {
    const [whole, fraction] = Math.abs(n).toFixed(decimals).split(".");
    const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
    return (n < 0 ? "-" : "") + (fraction ? `${grouped}.${fraction}` : grouped);
}

/** "42.120 OMR" / Arabic "42.120 ر.ع.": an amount in NuqtaPass's currency. */
export function formatMoney(amount, currency, lang = "en") {
    if (!currency) {
        return formatNumber(amount, Number.isInteger(amount) ? 0 : 3).replace(/\.?0+$/, "") || "0";
    }
    const arabic = String(lang || "").startsWith("ar");
    const label = (arabic && ARABIC_SYMBOLS[currency.code]) || currency.code;
    return `${formatNumber(amount, currency.decimals)} ${label}`;
}

/** What a cashier typed in a money box (Arabic digits and decimal sign too), or NaN. */
export function parseMoney(text) {
    let value = String(text ?? "")
        .trim()
        .replace(/[٠-٩]/g, (d) => String(d.charCodeAt(0) - 0x0660))
        .replace(/[۰-۹]/g, (d) => String(d.charCodeAt(0) - 0x06f0))
        .replace(/٫/g, ".")
        .replace(/٬/g, ",")
        .replace(/\s/g, "");
    value = value.includes(".") ? value.replace(/,/g, "") : value.replace(",", ".");
    if (!/^\d+(\.\d+)?$/.test(value)) {
        return Number.NaN;
    }
    return Number(value);
}
