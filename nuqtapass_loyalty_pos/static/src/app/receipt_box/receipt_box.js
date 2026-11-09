import { Component, useState } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { ReceiptScreen } from "@point_of_sale/app/screens/receipt_screen/receipt_screen";
import { FeedbackScreen } from "@point_of_sale/app/screens/feedback_screen/feedback_screen";
import { useBarcodeReader } from "@point_of_sale/app/hooks/barcode_reader_hook";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { attachToOrder, earnedLine, scanKind, welcomeWithQr } from "../nuqtapass_api";

/**
 * Under "Payment Successful", for a paid order with no customer phone: type the phone or scan the Wallet card, and
 * the order earns now. Then the box shows what it earned, or the QR code when the card isn't on a phone yet.
 *
 * Odoo 19: the screen after payment is ReceiptScreen (Print / Send / New Order, no auto-continue). FeedbackScreen
 * only shows when the till prints automatically and skips the receipt screen; it continues by itself after 1.5 s,
 * and using the box stops that. (Odoo 20 has only FeedbackScreen.)
 */
export class NuqtaPassReceiptBox extends Component {
    static template = "nuqtapass_loyalty_pos.ReceiptBox";
    // Odoo 19 (OWL 2): static props, useState (20.0 uses useProps / proxy).
    static props = {
        order: Object,
        // Called when the cashier uses the box (FeedbackScreen stops its auto-continue).
        onUse: Function,
    };

    setup() {
        this.pos = usePos();
        this.barcodeReader = useService("barcode_reader");
        this.state = useState({ query: "", busy: false, error: "", line: "", welcome: null, answered: false });
        // A scan while the box isn't focused still lands here (the product screen isn't listening now).
        useBarcodeReader({ product: (code) => this.onScan(code) });
    }

    onScan(code) {
        if (this.state.answered || !scanKind(code.code)) {
            this.barcodeReader?.showNotFoundNotification(code);
            return;
        }
        this.state.query = code.code;
        return this.add();
    }

    async add() {
        const query = this.state.query.trim();
        if (!query || this.state.busy) {
            return;
        }
        this.props.onUse();
        this.state.busy = true;
        this.state.error = "";
        const res = await attachToOrder(this.pos.config.id, this.props.order.id, query);
        this.state.busy = false;
        if (!res.ok) {
            this.state.error = res.message;
            return;
        }
        this.state.answered = true;
        this.props.order.nuqtapass_phone = res.phone;
        this.state.line = res.pending ? res.message : earnedLine(res.earned, res.card);
        this.state.welcome = res.show_qr ? welcomeWithQr(res.welcome) : null;
    }

    get title() {
        return _t("Earn NuqtaPass points");
    }
}

/** A paid order of this till, in Odoo (it has a server id), that earns and has no customer phone yet. */
function nuqtapassAsk(screen, loading) {
    const order = screen.currentOrder;
    return Boolean(
        screen.pos.config.nuqtapass_till_on &&
            !loading &&
            order &&
            typeof order.id === "number" &&
            order.amount_total > 0 &&
            !order.nuqtapass_phone &&
            !order.partner_id?.phone
    );
}

for (const Screen of [ReceiptScreen, FeedbackScreen]) {
    patch(Screen, {
        components: { ...Screen.components, NuqtaPassReceiptBox },
    });
}

patch(ReceiptScreen.prototype, {
    get nuqtapassAsk() {
        return nuqtapassAsk(this, false);
    },

    nuqtapassUse() {
        this.nuqtapassAsked = true; // keep the box (and its answer) once the cashier has used it
    },
});

patch(FeedbackScreen.prototype, {
    get nuqtapassAsk() {
        return nuqtapassAsk(this, this.state.loading);
    },

    nuqtapassUse() {
        this.nuqtapassAsked = true;
        // Odoo 19's FeedbackScreen continues after 1.5 s (this.timeout): the cashier is using the box, so stay.
        clearTimeout(this.timeout);
    },
});
