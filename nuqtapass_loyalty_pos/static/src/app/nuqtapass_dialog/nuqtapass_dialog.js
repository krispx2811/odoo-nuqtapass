import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { cardLine, cardTitle, lookUpCustomer, redeemOnCard, startingPoints, welcomeWithQr } from "../nuqtapass_api";

export class NuqtaPassDialog extends Component {
    static template = "nuqtapass_loyalty_pos.NuqtaPassDialog";
    static components = { Dialog };
    // Odoo 19 (OWL 2): static props + defaultProps, useState (20.0 uses useProps / proxy).
    static props = {
        configId: Number,
        startingPhone: { type: String, optional: true },
        // Set when the window opens after payment to show a new card's QR code.
        cardUrl: { type: String, optional: true },
        whatsapp: { type: String, optional: true },
        sms: { type: String, optional: true },
        onUsePhone: Function,
        close: Function,
    };
    static defaultProps = { startingPhone: "", cardUrl: "", whatsapp: "", sms: "" };

    setup() {
        this.state = useState({
            phone: this.props.startingPhone,
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
        if (this.props.startingPhone) {
            this.lookUp();
        }
    }

    get qrOnly() {
        return Boolean(this.props.cardUrl);
    }

    cardLine(card) {
        return cardLine(card);
    }

    cardTitle(card) {
        return cardTitle(card);
    }

    async lookUp() {
        if (!this.state.phone.trim() || this.state.loading) {
            return;
        }
        this.state.loading = true;
        this.state.error = "";
        this.state.done = "";
        const res = await lookUpCustomer(this.props.configId, this.state.phone.trim());
        this.state.loading = false;
        if (res.ok) {
            this.state.result = res;
            this.state.phone = res.phone;
            this.state.points = startingPoints(res.cards);
            this.state.welcome = res.walletAdded ? null : welcomeWithQr(res.welcome);
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
            await this.lookUp();
            this.state.done = res.message;
        } else {
            this.state.error = res.message;
        }
    }

    usePhone() {
        this.props.onUsePhone(this.state.result.phone);
        this.props.close();
    }

    get title() {
        return _t("NuqtaPass");
    }
}
