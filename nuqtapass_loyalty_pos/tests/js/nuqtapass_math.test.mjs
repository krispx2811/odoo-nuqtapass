// The till's NuqtaPass money math (static/src/app/pay/nuqtapass_math.js). Run: node --test nuqtapass_loyalty_pos/tests/js
import { test } from "node:test";
import assert from "node:assert/strict";
import {
    creditAmount,
    fitPoints,
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

test("points for an amount round down to whole points", () => {
    assert.equal(pointsFor(5, 33.333333), 166); // 166.67 → 166
    assert.equal(pointsFor(1, 33.333333), 33); // 33.33 → 33 (not 34 = 1.020 off)
    assert.equal(pointsFor(5, 10), 50); // exact stays exact
    assert.equal(pointsFor(0.1 + 0.2, 10), 3); // float noise does not lose a point
    assert.equal(pointsFor(0, 10), 0);
});

test("the discount is the value of those whole points, at the currency's decimals", () => {
    assert.equal(valueOfPoints(167, 33.333333, 3), 5.01);
    assert.equal(valueOfPoints(167, 33.333333, 2), 5.01);
    assert.equal(valueOfPoints(7, 3, 2), 2.33);
    assert.equal(valueOfPoints(7, 3, 0), 2);
    assert.equal(valueOfPoints(50, 10, 3), 5);
});

test("planPoints: part of the order rounds down; never more off than was typed", () => {
    const base = { ppu: 33.333333, decimals: 3, cardPoints: 1444, capPoints: null, maxValue: 100 };
    const plan = (extra) => planPoints({ ...base, ...extra });
    assert.deepEqual(plan({ amount: 5 }), { points: 166, value: 4.98, capped: null });
    assert.deepEqual(plan({ amount: 1 }), { points: 33, value: 0.99, capped: null }); // not 34 = 1.020 off
    assert.deepEqual(plan({ amount: 10.5 }), { points: 350, value: 10.5, capped: null });
    // A typed amount with more decimals than the currency: the rounded value stays at or under it.
    assert.deepEqual(planPoints({ ppu: 3, decimals: 2, cardPoints: 100, amount: 0.6666 }), { points: 1, value: 0.33, capped: null });
    // Nothing to use.
    assert.deepEqual(plan({ amount: 0 }), { points: 0, value: 0, capped: null });
    assert.deepEqual(plan({ amount: Number.NaN }), { points: 0, value: 0, capped: null });
    assert.deepEqual(plan({ amount: 5, ppu: null }), { points: 0, value: 0, capped: null });
});

test("planPoints: the whole order rounds up to cover it, and comes off exactly (Kareem, 28.160 due)", () => {
    const base = { ppu: 33.333333, decimals: 3, cardPoints: 1444, capPoints: null, maxValue: 28.16 };
    const plan = (extra) => planPoints({ ...base, ...extra });
    // 1 point = 0.030: 938 points (28.140) would leave 0.020 to pay; 939 points take off exactly 28.160.
    assert.deepEqual(plan({ amount: 28.16 }), { points: 939, value: 28.16, capped: null });
    const due = { reason: "due", value: 28.16 };
    assert.deepEqual(plan({ amount: 28.19 }), { points: 939, value: 28.16, capped: due });
    assert.deepEqual(plan({ amount: 30 }), { points: 939, value: 28.16, capped: due });
    // A bit less than the total, leaving less than one point to pay: one more point, the order comes to 0.
    assert.deepEqual(plan({ amount: 28.15 }), { points: 939, value: 28.16, capped: null });
    // More than one point's worth left to pay: still rounded down.
    assert.deepEqual(plan({ amount: 28.1 }), { points: 936, value: 28.08, capped: null });
    // The card can't cover it all: all of its points, and why.
    assert.deepEqual(plan({ amount: 30, cardPoints: 900 }), { points: 900, value: 27, capped: { reason: "card", value: 27 } });
    // Nor can the per-visit cap.
    assert.deepEqual(plan({ amount: 30, capPoints: 333 }), { points: 333, value: 9.99, capped: { reason: "cap", value: 9.99 } });
});

test("planPoints: less than one point's worth left to pay takes one more point (Kareem, 23.560 due)", () => {
    const base = { ppu: 33.333333, decimals: 3, cardPoints: 1444, capPoints: null, maxValue: 23.56 };
    // 785 points = 23.550 would leave 0.010: 786 points take off exactly 23.560.
    for (const amount of [23.56, 23.55, 25]) {
        assert.equal(planPoints({ ...base, amount }).points, 786);
        assert.equal(planPoints({ ...base, amount }).value, 23.56);
    }
    // The card has no 786th point: the floor stays, and the 0.010 is paid as usual.
    assert.deepEqual(planPoints({ ...base, amount: 23.56, cardPoints: 785 }), { points: 785, value: 23.55, capped: null });
    // Nor does the per-visit cap allow it.
    assert.deepEqual(planPoints({ ...base, amount: 23.56, capPoints: 785 }), { points: 785, value: 23.55, capped: null });
});

test("planPoints: more than the card has or the per-visit cap allows says so", () => {
    const base = { ppu: 33.333333, decimals: 3, cardPoints: 1404, capPoints: null, maxValue: 100 };
    assert.deepEqual(planPoints({ ...base, amount: 99 }), { points: 1404, value: 42.12, capped: { reason: "card", value: 42.12 } });
    assert.deepEqual(planPoints({ ...base, amount: 20, capPoints: 333 }), { points: 333, value: 9.99, capped: { reason: "cap", value: 9.99 } });
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

test("a till in US dollars still shows an Omani shop's points in OMR (Kareem, 2026-11-09)", () => {
    // The window formats with /customer's currency only; the till's own currency never reaches formatMoney.
    const card = { points: 1404, pointsValue: 42.12 };
    assert.equal(`${formatNumber(card.points)} points · worth ${formatMoney(card.pointsValue, OMR)}`,
        "1,404 points · worth 42.120 OMR");
    assert.equal(`${formatNumber(card.points)} نقطة · قيمتها ${formatMoney(card.pointsValue, OMR, "ar-001")}`,
        "1,404 نقطة · قيمتها 42.120 ر.ع.");
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

test("fitPoints: points that no longer fit the order's total (a free item went on) are lowered, never below 0", () => {
    const base = { ppu: 33.333333, decimals: 3 };
    // Still fits: unchanged.
    assert.deepEqual(fitPoints({ ...base, points: 166, value: 4.98, maxValue: 5 }), { points: 166, value: 4.98 });
    // 7.500 of points on an order now worth 2.500 without them: 84 points take off exactly 2.500 (the order: 0).
    assert.deepEqual(fitPoints({ ...base, points: 250, value: 7.5, maxValue: 2.5 }), { points: 84, value: 2.5 });
    // Nothing left on the order: no points.
    assert.deepEqual(fitPoints({ ...base, points: 250, value: 7.5, maxValue: 0 }), { points: 0, value: 0 });
    // The points card isn't known (no rate): the points come off.
    assert.deepEqual(fitPoints({ ppu: undefined, decimals: 3, points: 250, value: 7.5, maxValue: 2 }), { points: 0, value: 0 });
});
