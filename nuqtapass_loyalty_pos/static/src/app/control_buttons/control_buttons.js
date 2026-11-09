import { patch } from "@web/core/utils/patch";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { NuqtaPassDialog } from "../nuqtapass_dialog/nuqtapass_dialog";

patch(ControlButtons.prototype, {
    onClickNuqtaPass() {
        const order = this.currentOrder;
        this.dialog.add(NuqtaPassDialog, {
            configId: this.pos.config.id,
            startingPhone: order?.nuqtapass_phone || this.partner?.phone || "",
            onUsePhone: (phone) => {
                if (order) {
                    order.nuqtapass_phone = phone;
                }
            },
        });
    },
});
