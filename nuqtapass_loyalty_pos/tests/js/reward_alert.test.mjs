// The reward-ready notice (static/src/app/reward_alert.js): which of the customer's cards it tells the cashier about.
import { test } from "node:test";
import assert from "node:assert/strict";
import { rewardToAlert } from "../../static/src/app/reward_alert.js";

const stamps = (n, over = {}) => ({
    cardId: "s1", type: "STAMPS", stamps: n, stampsRequired: 6, rewardReady: n >= 6, current: true, ...over,
});
const voucher = (usesLeft, over = {}) => ({
    cardId: "v1", type: "VOUCHER", current: false, voucher: { id: "x", title: "Free cookie", usesLeft }, ...over,
});

test("a full stamp card: reward ready", () => {
    assert.deepEqual(rewardToAlert([stamps(6)]), { kind: "reward", cardId: "s1", stamps: 6, required: 6 });
});

test("an active voucher: its title", () => {
    assert.deepEqual(rewardToAlert([stamps(3), voucher(1)]), { kind: "voucher", cardId: "v1", title: "Free cookie" });
});

test("both: the stamp reward first", () => {
    assert.equal(rewardToAlert([voucher(1), stamps(6)]).kind, "reward");
});

test("nothing ready: no notice", () => {
    assert.equal(rewardToAlert([stamps(5), voucher(0)]), null);
    assert.equal(rewardToAlert([stamps(6, { current: false })]), null);
    assert.equal(rewardToAlert([]), null);
    assert.equal(rewardToAlert(undefined), null);
});
