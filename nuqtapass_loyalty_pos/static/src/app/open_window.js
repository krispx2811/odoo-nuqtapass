import { _t } from "@web/core/l10n/translation";
import { user } from "@web/core/user";
import { NuqtaPassDialog } from "./nuqtapass_dialog/nuqtapass_dialog";
import { rewardToAlert } from "./reward_alert";

let closeOpenWindow = null;

/**
 * Open the NuqtaPass window for the till's current order: whoever is found there becomes the order's NuqtaPass
 * customer (order.nuqtapass_phone, used before the Odoo customer's phone). One window at a time.
 */
export function openNuqtaPassWindow(pos, { query = "", result = null } = {}) {
    const order = pos.getOrder();
    const open = Boolean(order && !order.finalized);
    closeOpenWindow?.();
    closeOpenWindow = pos.dialog.add(
        NuqtaPassDialog,
        {
            configId: pos.config.id,
            startingQuery: query,
            ...(result ? { startingResult: result } : {}),
            forOrder: open,
            onCustomer: (phone) => {
                if (open && phone) {
                    order.nuqtapass_phone = phone;
                }
            },
            onFound: (res) => open && alertReward(pos, order, res.cards),
        },
        { onClose: () => (closeOpenWindow = null) }
    );
}

/**
 * The reward-ready notice (spec 2026-11-09 §2): when a customer is set on an order and their stamp card is full or
 * they hold an active voucher, a short notice with one button. Not blocking, and once per order.
 *  - open order: the button goes to the payment screen, its NuqtaPass panel pointing at that card (or `onUse`, when
 *    the panel is already showing);
 *  - paid order (the customer added on the receipt screen): the button opens the NuqtaPass window to give it now.
 */
export function alertReward(pos, order, cards, { onUse = null } = {}) {
    if (!order || !pos.config.nuqtapass_till_on || order.uiState?.nuqtapassAlerted) {
        return false;
    }
    const alert = rewardToAlert(cards, user.lang);
    if (!alert) {
        return false;
    }
    order.uiState.nuqtapassAlerted = true;
    // The till's page reads left to right even in Arabic: an Arabic notice is its own right-to-left run, and the
    // shop's reward (often English) is isolated inside it, so "المكافأة جاهزة: Free coffee" keeps its order.
    const arabic = String(user.lang || "").startsWith("ar");
    const reward = `\u2068${alert.reward}\u2069`;
    const title = `\u2068${alert.title}\u2069`;
    const text =
        alert.kind === "reward"
            ? alert.reward
                ? _t("Reward ready: %(reward)s", { reward })
                : _t("Reward ready: %(stamps)s of %(required)s stamps", { stamps: alert.stamps, required: alert.required })
            : _t("Voucher: %(title)s", { title });
    const message = arabic ? `\u2067${text}\u2069` : text;
    const paid = Boolean(order.finalized);
    let close = null;
    const use = () => {
        close?.();
        if (onUse) {
            onUse(alert.cardId);
        } else if (paid) {
            openNuqtaPassWindow(pos, { query: order.nuqtapass_phone || order.partner_id?.phone || "" });
        } else {
            closeOpenWindow?.();
            order.uiState.nuqtapassFocus = alert.cardId;
            pos.navigate("PaymentScreen", { orderUuid: order.uuid });
        }
    };
    close = pos.notification.add(message, {
        type: "info",
        title: _t("NuqtaPass"),
        autocloseDelay: 12000,
        buttons: [{ name: paid ? _t("Open NuqtaPass") : _t("Use at payment"), primary: true, onClick: use }],
    });
    return true;
}
