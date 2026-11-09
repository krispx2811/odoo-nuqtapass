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

/** Whole points needed for `amount` of money: always rounded up. */
export function pointsFor(amount, pointsPerUnit) {
    if (!usable(amount) || !usable(pointsPerUnit)) {
        return 0;
    }
    return Math.ceil(amount * pointsPerUnit - 1e-6);
}

/** The money value of whole points, rounded to the currency's decimals. */
export function valueOfPoints(points, pointsPerUnit, decimals) {
    if (!usable(points) || !usable(pointsPerUnit)) {
        return 0;
    }
    return roundTo(points / pointsPerUnit, decimals);
}

/**
 * The points line for a typed amount: points = ceil(amount × points per unit), no more than the card has or the
 * shop's per-visit cap allows, and never worth more than `maxValue` (the order's total). The discount is the value
 * of those whole points.
 */
export function planPoints({ amount, ppu, decimals, cardPoints, capPoints = null, maxValue = Infinity }) {
    let points = pointsFor(amount, ppu);
    points = Math.min(points, Math.max(0, Math.floor(cardPoints || 0)));
    if (capPoints !== null && capPoints !== undefined) {
        points = Math.min(points, Math.max(0, capPoints));
    }
    if (points > 0 && valueOfPoints(points, ppu, decimals) > maxValue + EPS) {
        points = Math.max(0, Math.floor(maxValue * ppu + 1e-6));
        while (points > 0 && valueOfPoints(points, ppu, decimals) > maxValue + EPS) {
            points -= 1;
        }
    }
    return points > 0 ? { points, value: valueOfPoints(points, ppu, decimals) } : { points: 0, value: 0 };
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
