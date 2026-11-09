import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { findCustomer, scanKind } from "../nuqtapass_api";
import { openNuqtaPassWindow } from "../open_window";

// NuqtaPass answers that mean "not a NuqtaPass card here": Odoo then handles the scan as usual (not found).
const ODOO_HANDLES = new Set(["card_not_found", "not_found", "invalid_phone", "disabled", "not_configured"]);

/**
 * A Wallet card scanned on the product screen. Odoo's barcode_reader hands every scan the nomenclature calls a
 * product (the default rule `.*` matches a card id or a phone) to `_barcodeProductAction`; we look first:
 * - a card id (UUID) goes to NuqtaPass;
 * - a phone (8-15 digits) only when no product has that barcode (an EAN-8 can look like an Omani mobile);
 * - anything else, or a card NuqtaPass doesn't know, stays Odoo's (product, or "Unknown Barcode").
 */
patch(ProductScreen.prototype, {
    setup() {
        const result = super.setup(...arguments);
        this.nuqtapassNotification = useService("notification");
        return result;
    },

    async _barcodeProductAction(code) {
        const kind = this.pos.config.nuqtapass_till_on ? scanKind(code.code) : "";
        if (kind === "card" || (kind === "phone" && !(await this._getProductByBarcode(code)))) {
            const res = await findCustomer(this.pos.config.id, code.code);
            if (res.ok) {
                this.sound.play("beep");
                openNuqtaPassWindow(this.pos, { result: res });
                return;
            }
            if (!ODOO_HANDLES.has(res.error)) {
                // NuqtaPass can't be reached or refused: say so rather than "Unknown Barcode".
                this.sound.play("scan-error");
                this.nuqtapassNotification.add(res.message, { type: "warning", title: "NuqtaPass" });
                return;
            }
        }
        return super._barcodeProductAction(code);
    },
});
