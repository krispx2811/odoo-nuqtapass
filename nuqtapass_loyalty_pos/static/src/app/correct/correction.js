// A POS manager's correction from the NuqtaPass window: what the till sends to /nuqtapass_loyalty/pos/adjust, or why
// not. The server checks it all again. Plain JS: tests/js/correction.test.mjs.

export const REASON_MIN = 3;
export const REASON_MAX = 200;
const MAX_DELTA = 1_000_000;
const ACTIONS = { STAMPS: ["stamp_add", "stamp_undo"], POINTS: ["points"] };

/** "+50", "-40", "−40", "1,000", "٢٣٠" → a whole number; null for anything else. */
function wholePoints(text) {
    const latin = String(text ?? "")
        .trim()
        .replace(/[٠-٩]/g, (d) => String(d.charCodeAt(0) - 0x0660))
        .replace(/−/g, "-")
        .replace(/,/g, "");
    return /^[+-]?\d+$/.test(latin) ? Number(latin) : null;
}

/** { ok: true, body: { card_id, action, delta, reason } } or { ok: false, error: "action" | "points" | "reason" }. */
export function correctionBody(card, { action, points, reason }) {
    if (!(ACTIONS[card?.type] || []).includes(action)) {
        return { ok: false, error: "action" };
    }
    let delta = null;
    if (action === "points") {
        delta = wholePoints(points);
        if (!delta || Math.abs(delta) > MAX_DELTA) {
            return { ok: false, error: "points" };
        }
    }
    const why = String(reason ?? "").trim();
    if (why.length < REASON_MIN || why.length > REASON_MAX) {
        return { ok: false, error: "reason" };
    }
    return { ok: true, body: { card_id: card.cardId, action, delta, reason: why } };
}
