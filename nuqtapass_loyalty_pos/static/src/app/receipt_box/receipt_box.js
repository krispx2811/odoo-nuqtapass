import { Component, useProps, proxy, t } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { FeedbackScreen } from "@point_of_sale/app/screens/feedback_screen/feedback_screen";
import { useBarcodeReader } from "@point_of_sale/app/hooks/barcode_reader_hook";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { attachToOrder, earnedLine, scanKind, welcomeWithQr } from "../nuqtapass_api";
import { alertReward } from "../open_window";

/**
 * Under "Amount Paid", for a paid order with no customer phone: type the phone or scan the Wallet card, and the
 * order earns now. Then the box shows what it earned, or the QR code when the card isn't on a phone yet.
 */
export class NuqtaPassReceiptBox extends Component {
    static template = "nuqtapass_loyalty_pos.ReceiptBox";
    props = useProps({
        order: t.object(),
        // The screen's own auto-continue stops while the cashier uses the box.
        onUse: t.function(),
    });

    setup() {
        this.pos = usePos();
        this.barcodeReader = useService("barcode_reader");
        this.state = proxy({ query: "", busy: false, error: "", line: "", welcome: null, answered: false });
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
        alertReward(this.pos, this.props.order, res.cards || []);
    }

    get title() {
        return _t("Earn NuqtaPass points");
    }
}

patch(FeedbackScreen, {
    components: { ...FeedbackScreen.components, NuqtaPassReceiptBox },
});

patch(FeedbackScreen.prototype, {
    /** A paid order of this till, in Odoo (it has a server id), that earns and has no customer phone yet. */
    get nuqtapassAsk() {
        const order = this.currentOrder;
        return Boolean(
            this.pos.config.nuqtapass_till_on &&
                !this.loading() &&
                order &&
                typeof order.id === "number" &&
                order.amount_total > 0 &&
                !order.nuqtapass_phone &&
                !order.partner_id?.phone
        );
    },

    nuqtapassUse() {
        this.nuqtapassAsked = true; // keep the box (and its answer) once the cashier has used it
        this.stopAutomaticSkip();
    },
});
