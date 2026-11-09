// What the reward-ready notice tells the cashier when a customer is set on an order: a full current stamp card
// first, else an active voucher. Plain JS: tests/js/reward_alert.test.mjs.

/** { kind: "reward", cardId, stamps, required, reward } / { kind: "voucher", cardId, title } / null. `reward`: the
 * card's own reward in the till's language (an Arabic till: its Arabic text if NuqtaPass sends one, else the shop's
 * text), or "" when the shop has none of its own: the notice then counts the stamps. */
export function rewardToAlert(cards, lang = "") {
    const list = cards || [];
    const full = list.find((c) => c.type === "STAMPS" && c.current !== false && c.rewardReady);
    if (full) {
        return {
            kind: "reward",
            cardId: full.cardId,
            stamps: full.stamps,
            required: full.stampsRequired,
            reward: rewardName(full, lang),
        };
    }
    const voucher = list.find((c) => c.type === "VOUCHER" && (c.voucher?.usesLeft ?? 0) > 0);
    return voucher ? { kind: "voucher", cardId: voucher.cardId, title: voucher.voucher.title || "" } : null;
}

/** A card's own reward in the till's language, or "". */
export function rewardName(card, lang = "") {
    const arabic = String(lang || "").startsWith("ar");
    const text = (arabic && card?.rewardTextAr) || card?.rewardText;
    return typeof text === "string" ? text.trim() : "";
}
