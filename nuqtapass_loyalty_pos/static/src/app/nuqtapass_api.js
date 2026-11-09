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

export function lookUpCustomer(configId, phone) {
    return call("/nuqtapass_loyalty/pos/customer", { config_id: configId, phone });
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

/** A Part 1 PosCard's one line: where it stands. */
export function cardLine(card) {
    switch (card.type) {
        case "STAMPS":
            return _t("%(stamps)s of %(required)s stamps", { stamps: card.stamps, required: card.stampsRequired });
        case "POINTS":
            return _t("%(points)s points", { points: card.points });
        case "PREPAID":
            return _t("Balance: %(balance)s", { balance: card.balance });
        case "PACK":
            return _t("%(uses)s uses left", { uses: card.packUses });
        default:
            return _t("%(uses)s uses left", { uses: card.voucher?.usesLeft ?? 0 });
    }
}

/** The points box starts with all of the first points card's points (Part 1 caps a visit itself). */
export function startingPoints(cards) {
    const card = (cards || []).find((c) => c.type === "POINTS" && c.points > 0);
    return card ? String(card.points) : "";
}
