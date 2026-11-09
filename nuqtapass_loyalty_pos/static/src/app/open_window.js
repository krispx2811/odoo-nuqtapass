import { NuqtaPassDialog } from "./nuqtapass_dialog/nuqtapass_dialog";

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
            // Odoo 19: the till formats money with env.utils (20.0: pos.formatCurrency).
            formatCurrency: (amount) => pos.env.utils.formatCurrency(amount),
            onCustomer: (phone) => {
                if (open && phone) {
                    order.nuqtapass_phone = phone;
                }
            },
        },
        { onClose: () => (closeOpenWindow = null) }
    );
}
