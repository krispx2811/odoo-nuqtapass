import { patch } from "@web/core/utils/patch";
import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";

// A NuqtaPass line shows its own name ("NuqtaPass points", "Reward: free Flat white"), not the product's.
patch(PosOrderline.prototype, {
    setFullProductName() {
        if (this.nuqtapass_label) {
            this.full_product_name = this.nuqtapass_label;
            return;
        }
        return super.setFullProductName(...arguments);
    },

    get orderDisplayProductName() {
        if (this.nuqtapass_label) {
            return { name: this.nuqtapass_label, attributeString: "" };
        }
        return super.orderDisplayProductName;
    },
});
