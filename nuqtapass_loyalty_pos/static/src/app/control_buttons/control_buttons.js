import { patch } from "@web/core/utils/patch";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { openNuqtaPassWindow } from "../open_window";

patch(ControlButtons.prototype, {
    onClickNuqtaPass() {
        const order = this.currentOrder;
        openNuqtaPassWindow(this.pos, { query: order?.nuqtapass_phone || this.partner?.phone || "" });
    },
});
