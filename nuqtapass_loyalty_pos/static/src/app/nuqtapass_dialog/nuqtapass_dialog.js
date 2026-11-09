import { Component, useProps, proxy, signal, t } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { useAutofocus } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { NuqtaPassPointsBox } from "../pay/points_box";
import { setPointsLine, totalWithoutPoints } from "../pay/nuqtapass_lines";
import { formatNumber } from "../pay/nuqtapass_math";
import {
    bandStyle,
    cardLine,
    cardTitle,
    displayPhone,
    findCustomer,
    money,
    redeemOnCard,
    tierInfo,
    welcomeWithQr,
    willEarnLine,
} from "../nuqtapass_api";

/**
 * The NuqtaPass window: find the customer (phone typed, or the Wallet card scanned into the box), see their current
 * cards with one action each, and the order earns for them (no button: finding them sets them on the order).
 */
export class NuqtaPassDialog extends Component {
    static template = "nuqtapass_loyalty_pos.NuqtaPassDialog";
    static components = { Dialog, NuqtaPassPointsBox };
    props = useProps({
        configId: t.number(),
        startingQuery: t.string().optional(""),
        // Already found (a scan on the product screen): shown without a second look-up.
        startingResult: t.object().optional(),
        // True when an open order will earn for whoever is found here.
        forOrder: t.boolean().optional(false),
        // Set when the window opens after payment to show a new card's QR code.
        cardUrl: t.string().optional(""),
        whatsapp: t.string().optional(""),
        sms: t.string().optional(""),
        onCustomer: t.function().optional(),
        close: t.function(),
    });

    inputRef = signal.ref();

    setup() {
        this.pos = usePos();
        // A 2D scanner types into the focused box and presses Enter (Odoo's barcode service leaves inputs alone).
        useAutofocus({ ref: this.inputRef });
        this.state = proxy({
            query: this.props.startingQuery,
            loading: false,
            error: "",
            done: "",
            result: null,
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

    get tier() {
        return this.state.result ? tierInfo(this.state.result.cards) : null;
    }

    bandStyle(card) {
        return bandStyle(card, this.tier);
    }

    cardTitle(card) {
        return cardTitle(card);
    }

    cardLine(card) {
        return cardLine(card, this.state.result?.currency || null);
    }

    /** The open order this window works on (points go on it as a discount line), or null. */
    get order() {
        const order = this.props.forOrder ? this.pos.getOrder() : null;
        return order && !order.finalized ? order : null;
    }

    canUsePoints(card) {
        return Boolean(this.order && card.type === "POINTS" && card.points > 0 && card.pointsPerUnit > 0);
    }

    get maxPointsValue() {
        return this.order ? totalWithoutPoints(this.order) : 0;
    }

    /** Spent at payment, not now: the line can be removed at no cost. */
    async usePoints(card, plan) {
        const lines = await setPointsLine(this.pos, this.order, card, plan);
        if (lines.length) {
            this.state.error = "";
            this.state.done = _t("Added to the order: %(value)s off for %(points)s points. They're used when you validate.", {
                value: money(plan.value, this.state.result.currency),
                points: formatNumber(plan.points),
            });
        }
    }

    /** Rewards, vouchers, credit and packs are used on the payment screen for an open order. */
    get atPaymentHint() {
        return Boolean(
            this.order &&
                this.state.result?.cards.some(
                    (c) =>
                        (c.type === "STAMPS" && c.rewardReady) ||
                        (c.type === "VOUCHER" && c.voucher?.usesLeft > 0) ||
                        (c.type === "PREPAID" && c.balance > 0) ||
                        (c.type === "PACK" && (c.usesLeft || c.packUses) > 0)
                )
        );
    }

    show(res) {
        this.state.result = res;
        this.state.query = "";
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
        this.state.loading = true;
        this.state.error = "";
        this.state.done = "";
        const res = await redeemOnCard(this.props.configId, this.state.result.phone, card.cardId, action, {
            voucherId: action === "voucher" ? card.voucher?.id || null : null,
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
