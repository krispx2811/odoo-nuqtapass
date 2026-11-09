import { patch } from "@web/core/utils/patch";
import OrderPaymentValidation from "@point_of_sale/app/utils/order_payment_validation";
import { afterPayment } from "../nuqtapass_api";
import { NuqtaPassDialog } from "../nuqtapass_dialog/nuqtapass_dialog";

patch(OrderPaymentValidation.prototype, {
    async afterOrderValidation(...args) {
        const result = await super.afterOrderValidation(...args);
        this.nuqtapassShowCard().catch(() => {});
        return result;
    },

    async nuqtapassShowCard() {
        const order = this.order;
        const phone = order?.nuqtapass_phone || order?.partner_id?.phone;
        // A server id means the order reached Odoo (offline orders have none yet); refunds earn nothing.
        if (!phone || typeof order.id !== "number" || !(order.amount_total > 0)) {
            return;
        }
        const res = await afterPayment(this.pos.config.id, order.id);
        if (!res?.ok || !res.show_qr || !res.welcome?.cardUrl) {
            return;
        }
        this.pos.dialog.add(NuqtaPassDialog, {
            configId: this.pos.config.id,
            cardUrl: res.welcome.cardUrl,
            whatsapp: res.welcome.whatsapp || "",
            sms: res.welcome.sms || "",
        });
    },
});
