// A POS manager's correction (static/src/app/correct/correction.js): what the till sends to /adjust, or why not.
import { test } from "node:test";
import assert from "node:assert/strict";
import { correctionBody } from "../../static/src/app/correct/correction.js";

const stamp = { cardId: "s1", type: "STAMPS" };
const points = { cardId: "p1", type: "POINTS" };

test("a stamp: undo or add, with the reason trimmed", () => {
    assert.deepEqual(correctionBody(stamp, { action: "stamp_undo", reason: "  Pressed twice " }), {
        ok: true,
        body: { card_id: "s1", action: "stamp_undo", delta: null, reason: "Pressed twice" },
    });
    assert.equal(correctionBody(stamp, { action: "stamp_add", reason: "Missed one" }).body.action, "stamp_add");
});

test("points: a whole number, + or −, with thousands and Arabic digits", () => {
    const delta = (text) => correctionBody(points, { action: "points", points: text, reason: "Wrong sale" }).body?.delta;
    assert.equal(delta("+50"), 50);
    assert.equal(delta("50"), 50);
    assert.equal(delta("-40"), -40);
    assert.equal(delta("−40"), -40);
    assert.equal(delta("1,000"), 1000);
    assert.equal(delta("٢٣٠"), 230);
    assert.equal(delta(" -٥ "), -5);
});

test("points refused: 0, decimals, words, more than a million", () => {
    for (const text of ["0", "1.5", "abc", "", "+", "1000001", "--5"]) {
        assert.deepEqual(correctionBody(points, { action: "points", points: text, reason: "Wrong sale" }), {
            ok: false,
            error: "points",
        });
    }
});

test("a reason of 3 to 200 characters is required", () => {
    for (const reason of ["", "  ab ", "x".repeat(201), undefined]) {
        assert.deepEqual(correctionBody(stamp, { action: "stamp_add", reason }), { ok: false, error: "reason" });
    }
    assert.ok(correctionBody(stamp, { action: "stamp_add", reason: "x".repeat(200) }).ok);
});

test("the action must fit the card; other cards can't be corrected", () => {
    assert.deepEqual(correctionBody(stamp, { action: "points", points: "5", reason: "Wrong" }), { ok: false, error: "action" });
    assert.deepEqual(correctionBody(points, { action: "stamp_add", reason: "Wrong" }), { ok: false, error: "action" });
    assert.deepEqual(correctionBody({ cardId: "c", type: "PREPAID" }, { action: "points", points: "5", reason: "Wrong" }), {
        ok: false,
        error: "action",
    });
});
