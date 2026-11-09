// What the reward-ready notice tells the cashier when a customer is set on an order: a full current stamp card
// first, else an active voucher. Plain JS: tests/js/reward_alert.test.mjs.

/** { kind: "reward", cardId, stamps, required } / { kind: "voucher", cardId, title } / null. */
export function rewardToAlert(cards) {
    const list = cards || [];
    const full = list.find((c) => c.type === "STAMPS" && c.current !== false && c.rewardReady);
    if (full) {
        return { kind: "reward", cardId: full.cardId, stamps: full.stamps, required: full.stampsRequired };
    }
    const voucher = list.find((c) => c.type === "VOUCHER" && (c.voucher?.usesLeft ?? 0) > 0);
    return voucher ? { kind: "voucher", cardId: voucher.cardId, title: voucher.voucher.title || "" } : null;
}
