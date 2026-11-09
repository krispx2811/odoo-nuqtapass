// The tier line next to the customer (static/src/app/tiers.js): "Gold member · 10% cash-back", "230 more points to Gold".
import { test } from "node:test";
import assert from "node:assert/strict";
import { tierParts } from "../../static/src/app/tiers.js";

test("a Silver card: its cash-back and the points still to Gold", () => {
    const tier = { name: "SILVER", cashbackPct: 7.5, next: { name: "GOLD", pointsToGo: 3800 }, color: "rgb(213, 220, 228)" };
    assert.deepEqual(tierParts(tier), {
        name: "SILVER",
        pct: "7.5%",
        next: { name: "GOLD", points: "3,800" },
        color: "rgb(213, 220, 228)",
    });
});

test("Gold has no next tier; whole percents have no decimals; no colour is null", () => {
    assert.deepEqual(tierParts({ name: "GOLD", cashbackPct: 10, next: null }), {
        name: "GOLD",
        pct: "10%",
        next: null,
        color: null,
    });
    assert.equal(tierParts({ name: "BRONZE", cashbackPct: 2.25, next: { name: "SILVER", pointsToGo: 1 } }).pct, "2.25%");
});

test("no tier, or not one of the three: nothing to show", () => {
    assert.equal(tierParts(null), null);
    assert.equal(tierParts(undefined), null);
    assert.equal(tierParts({ name: "PLATINUM", cashbackPct: 1, next: null }), null);
});
