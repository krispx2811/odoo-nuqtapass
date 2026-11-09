import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { findCustomer } from "./nuqtapass_api";
import { alertReward } from "./open_window";

// An Odoo customer picked for the order (the customer list, or their barcode scanned): look their phone up at
// NuqtaPass, quietly, for the reward-ready notice. Nothing shows when NuqtaPass doesn't know them or can't be reached.
patch(PosStore.prototype, {
    setPartnerToCurrentOrder(partner) {
        const result = super.setPartnerToCurrentOrder(...arguments);
        const order = this.getOrder();
        const phone = partner?.phone || partner?.mobile;
        if (phone && this.config.nuqtapass_till_on && order && !order.finalized && !order.uiState?.nuqtapassAlerted) {
            findCustomer(this.config.id, phone).then((res) => {
                if (res.ok && this.getOrder() === order && order.partner_id === partner) {
                    alertReward(this, order, res.cards);
                }
            });
        }
        return result;
    },
});
