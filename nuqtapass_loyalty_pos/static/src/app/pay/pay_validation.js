import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { AlertDialog, ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import OrderPaymentValidation from "@point_of_sale/app/utils/order_payment_validation";
import { spendUses } from "../nuqtapass_api";
import { belowZero, creditPayment, nuqtapassLines, orderUses, pointsLines, removeAllNuqtaPass } from "./nuqtapass_lines";

/**
 * Validate spends the order's NuqtaPass uses (points, credit, a pack use, a reward, vouchers) before Odoo takes the
 * payment: the server calls NuqtaPass once per use with the order's receipt number, so a second press or a retry
 * spends nothing more. Any refusal or no connection stops the payment with NuqtaPass's words.
 */
patch(OrderPaymentValidation.prototype, {
    async askBeforeValidation(...args) {
        if ((await super.askBeforeValidation(...args)) === false) {
            return false;
        }
        return this.nuqtapassSpend();
    },

    async nuqtapassSpend() {
        const order = this.order;
        const credit = order && !order.isRefund ? creditPayment(order) : null;
        if (credit && !credit.nuqtapass_card_id && credit.getAmount() > 0) {
            // A NuqtaPass credit line that no customer's card is behind (e.g. an order reopened from elsewhere):
            // never taken as plain money that NuqtaPass doesn't spend.
            this.pos.dialog.add(AlertDialog, {
                title: _t("NuqtaPass"),
                body: _t("Remove the NuqtaPass credit line and add it again with the customer looked up."),
            });
            return false;
        }
        const uses = order && !order.isRefund ? orderUses(order) : [];
        if (!uses.length) {
            return true;
        }
        if (nuqtapassLines(order).length && belowZero(this.pos, order)) {
            // An item removed after its points or free item went on: NuqtaPass would take off more than is left.
            this.pos.dialog.add(AlertDialog, {
                title: _t("NuqtaPass"),
                body: _t("The NuqtaPass lines take off more than is on the order. Lower the points or remove a free item, then validate."),
            });
            return false;
        }
        if (order.uiState.nuqtapassSpending) {
            return false; // the first press is still at NuqtaPass
        }
        order.uiState.nuqtapassSpending = true;
        this.pos.env.services.ui.block();
        let res;
        try {
            const phone = order.nuqtapass_phone || order.partner_id?.phone || "";
            res = await spendUses(this.pos.config.id, order.pos_reference, phone, uses);
        } finally {
            this.pos.env.services.ui.unblock();
            order.uiState.nuqtapassSpending = false;
        }
        if (res?.ok) {
            return true;
        }
        this.nuqtapassShowRefusal(order, uses, res || {});
        return false;
    },

    nuqtapassShowRefusal(order, uses, res) {
        const use = Number.isInteger(res.index) ? uses[res.index] : null;
        if (res.error === "unreachable") {
            this.pos.dialog.add(ConfirmationDialog, {
                title: _t("NuqtaPass"),
                body: res.message,
                confirmLabel: _t("Remove NuqtaPass lines"),
                confirm: () => removeAllNuqtaPass(order),
                cancel: () => {},
                cancelLabel: _t("Close"),
            });
            return;
        }
        if (res.error === "refused" && use) {
            this.pos.dialog.add(ConfirmationDialog, {
                title: _t("NuqtaPass"),
                body: res.message,
                confirmLabel: _t("Remove this line"),
                confirm: () => this.nuqtapassRemove(order, use),
                cancel: () => {},
                cancelLabel: _t("Close"),
            });
            return;
        }
        this.pos.dialog.add(AlertDialog, { title: _t("NuqtaPass"), body: res.message || "" });
    },

    nuqtapassRemove(order, use) {
        if (use.payment) {
            const payment = order.payment_ids.find((p) => p.uuid === use.ref);
            if (payment) {
                order.removePaymentline(payment);
            }
            return;
        }
        // Points: every one of its lines (one per tax group).
        const lines = use.use === "points" ? pointsLines(order) : nuqtapassLines(order).filter((l) => l.uuid === use.ref);
        for (const line of lines) {
            order.removeOrderline(line);
        }
    },
});
