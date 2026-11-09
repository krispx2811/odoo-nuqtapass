import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { useAutofocus } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import {
    cardLine,
    cardTitle,
    displayPhone,
    findCustomer,
    redeemOnCard,
    startingPoints,
    welcomeWithQr,
    willEarnLine,
} from "../nuqtapass_api";

/**
 * The NuqtaPass window: find the customer (phone typed, or the Wallet card scanned into the box), see their current
 * cards with one action each, and the order earns for them (no button: finding them sets them on the order).
 */
export class NuqtaPassDialog extends Component {
    static template = "nuqtapass_loyalty_pos.NuqtaPassDialog";
    static components = { Dialog };
    // Odoo 19 (OWL 2): static props + defaultProps, useState, useAutofocus by t-ref (20.0 uses useProps / proxy / signal.ref).
    static props = {
        configId: Number,
        startingQuery: { type: String, optional: true },
        // Already found (a scan on the product screen): shown without a second look-up.
        startingResult: { type: Object, optional: true },
        // True when an open order will earn for whoever is found here.
        forOrder: { type: Boolean, optional: true },
        formatCurrency: { type: Function, optional: true },
        // Set when the window opens after payment to show a new card's QR code.
        cardUrl: { type: String, optional: true },
        whatsapp: { type: String, optional: true },
        sms: { type: String, optional: true },
        onCustomer: { type: Function, optional: true },
        close: Function,
    };
    static defaultProps = { startingQuery: "", forOrder: false, cardUrl: "", whatsapp: "", sms: "" };

    setup() {
        // A 2D scanner types into the focused box and presses Enter (Odoo's barcode service leaves inputs alone).
        // Odoo 19: useAutofocus finds the input by t-ref="autofocus".
        useAutofocus();
        this.state = useState({
            query: this.props.startingQuery,
            loading: false,
            error: "",
            done: "",
            result: null,
            points: "",
            welcome: welcomeWithQr({
                cardUrl: this.props.cardUrl,
                whatsapp: this.props.whatsapp,
                sms: this.props.sms,
            }),
        });
        if (this.props.startingResult) {
            this.show(this.props.startingResult);
        } else if (this.props.startingQuery) {
            this.lookUp();
        }
    }

    get qrOnly() {
        return Boolean(this.props.cardUrl);
    }

    get title() {
        return _t("NuqtaPass");
    }

    get phoneText() {
        return displayPhone(this.state.result?.phone);
    }

    get willEarn() {
        return this.props.forOrder && this.state.result ? willEarnLine(this.state.result.cards) : "";
    }

    cardTitle(card) {
        return cardTitle(card);
    }

    cardLine(card) {
        return cardLine(card, this.props.formatCurrency || null);
    }

    show(res) {
        this.state.result = res;
        this.state.query = "";
        this.state.points = startingPoints(res.cards);
        this.state.welcome = res.walletAdded ? null : welcomeWithQr(res.welcome);
        this.props.onCustomer?.(res.phone);
    }

    async lookUp(query = this.state.query.trim()) {
        if (!query || this.state.loading) {
            return;
        }
        this.state.loading = true;
        this.state.error = "";
        this.state.done = "";
        const res = await findCustomer(this.props.configId, query);
        this.state.loading = false;
        if (res.ok) {
            this.show(res);
        } else {
            this.state.result = null;
            this.state.welcome = null;
            this.state.error = res.message;
        }
    }

    async redeem(card, action) {
        if (this.state.loading) {
            return;
        }
        let points = null;
        if (action === "reward" && card.type === "POINTS") {
            points = Number(this.state.points);
            if (!Number.isInteger(points) || points <= 0) {
                this.state.error = _t("Type how many points to use, as a whole number.");
                return;
            }
        }
        this.state.loading = true;
        this.state.error = "";
        this.state.done = "";
        const res = await redeemOnCard(this.props.configId, this.state.result.phone, card.cardId, action, {
            voucherId: action === "voucher" ? card.voucher?.id || null : null,
            points,
        });
        this.state.loading = false;
        if (res.ok) {
            await this.lookUp(this.state.result.phone);
            this.state.done = res.message;
        } else {
            this.state.error = res.message;
        }
    }
}
