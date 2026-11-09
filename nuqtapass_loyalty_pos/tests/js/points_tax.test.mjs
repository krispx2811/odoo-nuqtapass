// The NuqtaPass points line split by the order's taxes (static/src/app/pay/points_tax.js), as Odoo's own pos_loyalty
// discount lines: one negative line per tax group, weighted by the group's tax-included share.
import { test } from "node:test";
import assert from "node:assert/strict";
import { exactPointsTotal, splitPointsByTax } from "../../static/src/app/pay/points_tax.js";

const VAT5 = { id: 5, amount_type: "percent", price_include: false };
const VAT10_INCL = { id: 10, amount_type: "percent", price_include: true };
const FIXED = { id: 99, amount_type: "fixed", price_include: false };

const line = (taxes, included, excluded) => ({ taxes, included, excluded });

test("one taxed item: the points line takes its VAT, priced before tax", () => {
    // Cake 4.000 + 5 % = 4.200; 2.100 off (tax included) → −2.000 at 5 %, so VAT is on the 2.000 left.
    const parts = splitPointsByTax([line([VAT5], 4.2, 4.0)], { value: 2.1, points: 70, decimals: 3 });
    assert.deepEqual(parts, [{ taxes: [VAT5], priceUnit: -2, points: 70 }]);
});

test("a taxed and an untaxed item: one line per tax group, weighted by its share", () => {
    const parts = splitPointsByTax([line([VAT5], 4.2, 4.0), line([], 2.5, 2.5)], {
        value: 3.35,
        points: 111,
        decimals: 3,
    });
    assert.deepEqual(parts, [
        { taxes: [VAT5], priceUnit: -2, points: 70 },
        { taxes: [], priceUnit: -1.25, points: 41 },
    ]);
    assert.equal(parts.reduce((n, p) => n + p.points, 0), 111);
});

test("a price-included tax: the line is priced with the tax in", () => {
    const parts = splitPointsByTax([line([VAT10_INCL], 5.5, 5.0)], { value: 1.1, points: 37, decimals: 3 });
    assert.deepEqual(parts, [{ taxes: [VAT10_INCL], priceUnit: -1.1, points: 37 }]);
});

test("lines with the same taxes share one group; fixed taxes are left out of the group", () => {
    const parts = splitPointsByTax(
        [line([VAT5], 2.1, 2.0), line([VAT5, FIXED], 3.15, 3.0)],
        { value: 5.25, points: 175, decimals: 3 }
    );
    assert.deepEqual(parts, [{ taxes: [VAT5], priceUnit: -5, points: 175 }]);
});

test("never more than the order: the factor stops at 1", () => {
    const parts = splitPointsByTax([line([VAT5], 4.2, 4.0)], { value: 9, points: 300, decimals: 3 });
    assert.deepEqual(parts, [{ taxes: [VAT5], priceUnit: -4, points: 300 }]);
});

test("a free-item line nets its group down; a group at 0 or below gets nothing", () => {
    // Flat white 2.5 untaxed made free by a reward (−2.5): only the cake's group is left to discount.
    const parts = splitPointsByTax(
        [line([VAT5], 4.2, 4.0), line([], 2.5, 2.5), line([], -2.5, -2.5)],
        { value: 2.1, points: 70, decimals: 3 }
    );
    assert.deepEqual(parts, [{ taxes: [VAT5], priceUnit: -2, points: 70 }]);
});

test("nothing to weigh by (no lines): one untaxed line, as before", () => {
    assert.deepEqual(splitPointsByTax([], { value: 2, points: 67, decimals: 3 }), [
        { taxes: [], priceUnit: -2, points: 67 },
    ]);
});

test("prices round to the currency's decimals and every point lands on a line", () => {
    const parts = splitPointsByTax(
        [line([VAT5], 1.05, 1.0), line([], 1, 1), line([VAT10_INCL], 1, 0.909)],
        { value: 1, points: 10, decimals: 2 }
    );
    for (const part of parts) {
        assert.equal(part.priceUnit, Math.round(part.priceUnit * 100) / 100);
    }
    assert.equal(parts.reduce((n, p) => n + p.points, 0), 10);
});

test("Validate spends the split lines as one points use (the sum)", async () => {
    const { pointsUse } = await import("../../static/src/app/pay/points_tax.js");
    const lines = [
        { uuid: "a", nuqtapass_card_id: "card", nuqtapass_qty: 70, nuqtapass_label: "NuqtaPass points" },
        { uuid: "b", nuqtapass_card_id: "card", nuqtapass_qty: 41, nuqtapass_label: "NuqtaPass points" },
    ];
    assert.deepEqual(pointsUse(lines), {
        use: "points",
        card_id: "card",
        label: "NuqtaPass points",
        points: 111,
        ref: "a",
    });
    assert.equal(pointsUse([]), null);
});

test("the points lines take off exactly their value: the last line takes the rounding (Kareem, 28.160 due)", () => {
    // A 5 % line priced before tax; its tax is rounded per line, as the till does.
    const r3 = (n) => Math.round(n * 1000) / 1000;
    const taxed = (price) => ({
        price_unit: price,
        get priceExcl() { return this.price_unit; },
        get priceIncl() { return r3(this.price_unit * 1.05); },
        setUnitPrice(p) { this.price_unit = r3(p); },
    });
    const items = [taxed(13.41), taxed(13.41)]; // 14.081 + 14.081 = 28.162 due
    const value = 28.162;
    const parts = splitPointsByTax(
        items.map((l) => ({ taxes: [VAT5], included: l.priceIncl, excluded: l.priceExcl })),
        { value, points: 939, decimals: 3 }
    );
    const pointsLines = parts.map((p) => taxed(p.priceUnit));
    const order = { get priceIncl() { return r3([...items, ...pointsLines].reduce((n, l) => n + l.priceIncl, 0)); } };
    exactPointsTotal(order, pointsLines.at(-1), 28.162 - value, 3);
    assert.equal(order.priceIncl, 0);
    // An untaxed points line moves one for one.
    const plain = (price) => ({ price_unit: price, priceExcl: 0, get priceIncl() { return this.price_unit; },
        setUnitPrice(p) { this.price_unit = r3(p); } });
    const item = plain(28.16);
    const off = plain(-28.13);
    const order2 = { get priceIncl() { return r3(item.priceIncl + off.priceIncl); } };
    exactPointsTotal(order2, off, 0, 3);
    assert.equal(off.price_unit, -28.16);
    assert.equal(order2.priceIncl, 0);
});
