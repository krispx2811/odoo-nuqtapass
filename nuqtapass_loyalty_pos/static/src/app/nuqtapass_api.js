import { rpc } from "@web/core/network/rpc";
import { _t } from "@web/core/l10n/translation";
import { generateQRCodeDataUrl } from "@point_of_sale/utils";

export function offlineMessage() {
    return _t(
        "NuqtaPass can't be reached right now. The sale is saved and will earn when the connection is back."
    );
}

async function call(route, params) {
    try {
        return await rpc(route, params, { silent: true });
    } catch {
        return { ok: false, error: "unreachable", message: offlineMessage() };
    }
}

// Same shapes as nuqtapass_loyalty/lib/scan.py: a Wallet card's QR holds its id (a UUID); older passes hold a phone.
const CARD_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const PHONE = /^\+?\d{8,15}$/;

/** "card", "phone" or "" for anything else (a product barcode). */
export function scanKind(text) {
    const value = String(text || "").trim();
    if (CARD_ID.test(value)) {
        return "card";
    }
    let digits = value.replace(/[\s-]/g, "");
    if (digits.startsWith("00")) {
        digits = digits.slice(2);
    }
    return PHONE.test(digits) ? "phone" : "";
}

/** GET /customer by a phone or a Wallet card id: { ok, phone, cards (current only), walletAdded, welcome }. */
export function findCustomer(configId, query) {
    return call("/nuqtapass_loyalty/pos/customer", { config_id: configId, query });
}

/** Receipt screen: set the customer on a paid order and send it now: { ok, phone, earned, card, show_qr, welcome } */
export function attachToOrder(configId, orderId, query) {
    return call("/nuqtapass_loyalty/pos/attach", { config_id: configId, order_id: orderId, query });
}

/** Part 1 POST /redeem: `cardId` from /customer, the card's voucher id (or null), and for a points reward how many points. */
export function redeemOnCard(configId, phone, cardId, action, { voucherId = null, points = null } = {}) {
    return call("/nuqtapass_loyalty/pos/redeem", {
        config_id: configId,
        phone,
        card_id: cardId,
        action,
        voucher_id: voucherId,
        points,
    });
}

/** Right after payment: the server sends the order now and answers { show_qr, welcome } (Task 11). */
export function afterPayment(configId, orderId) {
    return call("/nuqtapass_loyalty/pos/after_payment", { config_id: configId, order_id: orderId });
}

/** The welcome links (already whitelisted on the server) with the card link drawn as a QR image, or null. */
export function welcomeWithQr(welcome) {
    if (!welcome?.cardUrl) {
        return null;
    }
    return {
        cardUrl: welcome.cardUrl,
        whatsapp: welcome.whatsapp || "",
        sms: welcome.sms || "",
        qr: generateQRCodeDataUrl(welcome.cardUrl, { width: 220, height: 220 }),
    };
}

/** A Part 1 PosCard's heading. */
export function cardTitle(card) {
    switch (card.type) {
        case "STAMPS":
            return _t("Stamp card");
        case "POINTS":
            return _t("Points card");
        case "PREPAID":
            return _t("Prepaid card");
        case "PACK":
            return _t("Service pack");
        default:
            return card.voucher?.title || _t("Voucher");
    }
}

function usesLeft(n) {
    // English needs "1 use left"; Arabic reads "label: number", so every count is right in both.
    return n === 1 ? _t("1 use left") : _t("%(uses)s uses left", { uses: n });
}

/** A Part 1 PosCard's one line: where it stands. The dialog shows it inside <bdi> so numbers keep their order.
 * `formatCurrency` (the till's) adds what the points are worth. */
export function cardLine(card, formatCurrency = null) {
    switch (card.type) {
        case "STAMPS":
            return _t("%(stamps)s of %(required)s stamps", { stamps: card.stamps, required: card.stampsRequired });
        case "POINTS":
            if (formatCurrency && card.pointsValue > 0) {
                // LRI…PDI: the amount ("$ 10.00", "10.000 ر.ع.") keeps its own order inside an Arabic line.
                const value = `\u2066${formatCurrency(card.pointsValue)}\u2069`;
                return card.points === 1
                    ? _t("1 point (%(value)s)", { value })
                    : _t("%(points)s points (%(value)s)", { points: card.points, value });
            }
            return card.points === 1 ? _t("1 point") : _t("%(points)s points", { points: card.points });
        case "PREPAID":
            return _t("Balance: %(balance)s", { balance: card.balance });
        case "PACK":
            return usesLeft(card.packUses);
        default:
            return usesLeft(card.voucher?.usesLeft ?? 0);
    }
}

/** The points box starts with all of the first points card's points (Part 1 caps a visit itself). */
export function startingPoints(cards) {
    const card = (cards || []).find((c) => c.type === "POINTS" && c.points > 0);
    return card ? String(card.points) : "";
}

/** "+96894176872" → "+968 9417 6872" (GCC and Jordan codes are 3 digits); anything else as it is. */
export function displayPhone(e164) {
    const match = /^\+(\d{3})(\d{4})(\d{4,5})$/.exec(e164 || "");
    return match ? `+${match[1]} ${match[2]} ${match[3]}` : e164 || "";
}

/** The window's line for what this order will earn, from the customer's current cards. */
export function willEarnLine(cards) {
    const types = new Set((cards || []).map((c) => c.type));
    if (types.has("POINTS")) {
        return _t("This order will earn points");
    }
    if (types.has("STAMPS")) {
        return _t("This order will earn stamps");
    }
    return _t("This order will earn for this customer");
}

/** The receipt box's result: "+3 points · 163 now" / "+1 stamp · 4 of 6 now", from /attach's earned + card. */
export function earnedLine(earned, card) {
    const stamps = earned?.stamps || 0;
    const points = earned?.points || 0;
    if (points > 0) {
        const plus = points === 1 ? _t("+1 point") : _t("+%(points)s points", { points });
        return card?.type === "POINTS" ? _t("%(earned)s · %(total)s now", { earned: plus, total: card.points }) : plus;
    }
    if (stamps > 0) {
        const plus = stamps === 1 ? _t("+1 stamp") : _t("+%(stamps)s stamps", { stamps });
        return card?.type === "STAMPS"
            ? _t("%(earned)s · %(stamps)s of %(required)s now", {
                  earned: plus,
                  stamps: card.stamps,
                  required: card.stampsRequired,
              })
            : plus;
    }
    return _t("Sent. Nothing to earn on this card for this order.");
}
