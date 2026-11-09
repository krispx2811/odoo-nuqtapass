// The till's NuqtaPass money math (static/src/app/pay/nuqtapass_math.js). Run: node --test nuqtapass_loyalty_pos/tests/js
import { test } from "node:test";
import assert from "node:assert/strict";
import {
    creditAmount,
    formatMoney,
    formatNumber,
    parseMoney,
    planPoints,
    pointsFor,
    startingAmount,
    valueOfPoints,
} from "../../static/src/app/pay/nuqtapass_math.js";

const OMR = { code: "OMR", symbol: "OMR", decimals: 3 };
const AED = { code: "AED", symbol: "AED", decimals: 2 };
const JPY = { code: "JPY", symbol: "JPY", decimals: 0 };

test("points for an amount round up to whole points", () => {
    assert.equal(pointsFor(5, 33.333333), 167); // 166.67 → 167
    assert.equal(pointsFor(5, 10), 50); // exact stays exact
    assert.equal(pointsFor(0.1 + 0.2, 10), 3); // float noise does not add a point
    assert.equal(pointsFor(0, 10), 0);
});

test("the discount is the value of those whole points, at the currency's decimals", () => {
    assert.equal(valueOfPoints(167, 33.333333, 3), 5.01);
    assert.equal(valueOfPoints(167, 33.333333, 2), 5.01);
    assert.equal(valueOfPoints(7, 3, 2), 2.33);
    assert.equal(valueOfPoints(7, 3, 0), 2);
    assert.equal(valueOfPoints(50, 10, 3), 5);
});

test("planPoints: the typed amount, capped by the card, the per-visit cap and the order", () => {
    const base = { ppu: 33.333333, decimals: 3, cardPoints: 1404, capPoints: null, maxValue: 100 };
    assert.deepEqual(planPoints({ ...base, amount: 5 }), { points: 167, value: 5.01 });
    // More than the card has: all of its points.
    assert.deepEqual(planPoints({ ...base, amount: 99 }), { points: 1404, value: 42.12 });
    // The shop's per-visit cap.
    assert.deepEqual(planPoints({ ...base, amount: 20, capPoints: 333 }), { points: 333, value: 9.99 });
    // Rounding up must not take the discount past the order's total: one point less.
    assert.deepEqual(planPoints({ ...base, amount: 5, maxValue: 5 }), { points: 166, value: 4.98 });
    // Nothing to use.
    assert.deepEqual(planPoints({ ...base, amount: 0 }), { points: 0, value: 0 });
    assert.deepEqual(planPoints({ ...base, amount: Number.NaN }), { points: 0, value: 0 });
    assert.deepEqual(planPoints({ ...base, amount: 5, ppu: null }), { points: 0, value: 0 });
});

test("startingAmount: the smallest of the order, the card's worth and the per-visit cap", () => {
    assert.equal(startingAmount({ orderTotal: 7.5, cardWorth: 42.12, capValue: null, decimals: 3 }), 7.5);
    assert.equal(startingAmount({ orderTotal: 70, cardWorth: 42.12, capValue: null, decimals: 3 }), 42.12);
    assert.equal(startingAmount({ orderTotal: 70, cardWorth: 42.12, capValue: 10, decimals: 3 }), 10);
    assert.equal(startingAmount({ orderTotal: 0, cardWorth: 42.12, capValue: 10, decimals: 3 }), 0);
    assert.equal(startingAmount({ orderTotal: 2.3456, cardWorth: 9, capValue: null, decimals: 2 }), 2.34);
});

test("creditAmount: never more than the balance or what is due", () => {
    assert.equal(creditAmount({ amount: 5, balance: 9, due: 7.5, decimals: 3 }), 5);
    assert.equal(creditAmount({ amount: 20, balance: 9, due: 7.5, decimals: 3 }), 7.5);
    assert.equal(creditAmount({ amount: 20, balance: 6.5, due: 7.5, decimals: 3 }), 6.5);
    assert.equal(creditAmount({ amount: -1, balance: 6.5, due: 7.5, decimals: 3 }), 0);
});

test("formatMoney: NuqtaPass's currency, never the till's", () => {
    assert.equal(formatMoney(42.12, OMR), "42.120 OMR");
    assert.equal(formatMoney(1234.5, OMR), "1,234.500 OMR");
    assert.equal(formatMoney(5, AED), "5.00 AED");
    assert.equal(formatMoney(1500, JPY), "1,500 JPY");
    // Arabic: a plain-text abbreviation for the Gulf currencies, the code for the others; Latin digits.
    assert.equal(formatMoney(42.12, OMR, "ar"), "42.120 ر.ع.");
    assert.equal(formatMoney(5, AED, "ar_001"), "5.00 د.إ");
    assert.equal(formatMoney(1500, JPY, "ar"), "1,500 JPY");
    // No currency from NuqtaPass (an older server): the number alone.
    assert.equal(formatMoney(5, null), "5");
});

test("formatNumber groups thousands", () => {
    assert.equal(formatNumber(1404), "1,404");
    assert.equal(formatNumber(1234567), "1,234,567");
    assert.equal(formatNumber(12), "12");
});

test("parseMoney reads what a cashier types, Arabic digits too", () => {
    assert.equal(parseMoney("5"), 5);
    assert.equal(parseMoney(" 5.250 "), 5.25);
    assert.equal(parseMoney("1,234.5"), 1234.5);
    assert.equal(parseMoney("٥٫٢٥"), 5.25);
    assert.equal(parseMoney("5,25"), 5.25); // a comma alone is the decimal point
    assert.ok(Number.isNaN(parseMoney("")));
    assert.ok(Number.isNaN(parseMoney("abc")));
    assert.ok(Number.isNaN(parseMoney("-3")));
});
