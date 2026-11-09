import { Component, useProps, proxy, t } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { cardLine, cardTitle, displayPhone, findCustomer, money, tierInfo } from "../nuqtapass_api";
import { user } from "@web/core/user";
import { boxText, creditAmount, creditPick, formatMoney, formatNumber, parseMoney } from "./nuqtapass_math";
import {
    cantAddLine,
    coverableLines,
    creditMethod,
    creditPayment,
    fitPointsLine,
    freeLineFits,
    lineFor,
    pointsLines,
    rewardProduct,
    setCreditPayment,
    setFreeLine,
    setPointsLine,
    totalWithoutPoints,
} from "./nuqtapass_lines";
import { NuqtaPassPointsBox } from "./points_box";
import { alertReward } from "../open_window";

/**
 * The payment screen's NuqtaPass panel: "what do you want to use?". Each of the customer's current cards with its one
 * use for this order. Using one only puts a line (or the credit payment) on the order; Validate spends it.
 */
export class NuqtaPassPayPanel extends Component {
    static template = "nuqtapass_loyalty_pos.PayPanel";
    static components = { NuqtaPassPointsBox };
    props = useProps({ order: t.object() });

    setup() {
        this.pos = usePos();
        // The reward-ready notice's card, when its button brought the cashier here.
        const focus = this.props.order.uiState?.nuqtapassFocus || "";
        if (focus) {
            delete this.props.order.uiState.nuqtapassFocus;
        }
        this.state = proxy({ query: "", loading: false, error: "", errorDetail: "", notice: "", result: null, credit: null, pick: {}, focus });
        const phone = this.props.order.nuqtapass_phone || this.props.order.partner_id?.phone;
        if (phone) {
            this.lookUp(phone);
        }
    }

    get order() {
        return this.props.order;
    }

    get currency() {
        return this.state.result?.currency || null;
    }

    get phoneText() {
        return displayPhone(this.state.result?.phone);
    }

    get cards() {
        return this.state.result?.cards || [];
    }

    get tier() {
        return tierInfo(this.cards);
    }


    async lookUp(query = this.state.query.trim()) {
        if (!query || this.state.loading) {
            return;
        }
        this.state.loading = true;
        this.state.error = "";
        this.state.errorDetail = "";
        const res = await findCustomer(this.pos.config.id, query);
        this.state.loading = false;
        if (!res.ok) {
            this.state.result = null;
            delete this.order.uiState.nuqtapassCards;
            this.state.error = res.message;
            this.state.errorDetail = res.detail || "";
            return;
        }
        this.state.result = res;
        // For the "NuqtaPass credit" payment method's button (the payment screen's own list).
        this.order.uiState.nuqtapassCards = res.cards;
        this.order.uiState.nuqtapassDecimals = this.decimals;
        this.state.query = "";
        this.order.nuqtapass_phone = res.phone;
        this.state.credit = null; // the default again: it follows the amount due until the cashier types
        if (this.state.focus) {
            this.focusCard(this.state.focus);
        }
        alertReward(this.pos, this.order, res.cards, { onUse: (cardId) => this.focusCard(cardId) });
    }

    /** Point at a card (the reward-ready notice's): highlighted and scrolled into view. */
    focusCard(cardId) {
        this.state.focus = cardId;
        requestAnimationFrame(() =>
            document.querySelector(".o_nuqtapass_pay .o_nuqtapass_focus")?.scrollIntoView({ block: "nearest" })
        );
    }

    changeCustomer() {
        this.state.result = null;
        delete this.order.uiState.nuqtapassCards;
        this.state.error = "";
        this.state.errorDetail = "";
    }

    // ── one strip per card ────────────────────────────────────────────
    cardTitle(card) {
        return cardTitle(card);
    }

    cardLine(card) {
        return cardLine(card, this.currency);
    }

    money(amount) {
        return money(amount, this.currency);
    }

    get currencyLabel() {
        return formatMoney(0, this.currency, user.lang).replace(/^[\d.,\s]+/, "");
    }

    get decimals() {
        return this.currency?.decimals ?? this.pos.currency.decimal_places;
    }

    /** Why this card can't be used on this order right now (shown in its place), or "" when its action shows. */
    notNow(card) {
        const ready = card.type === "PREPAID" ? creditMethod(this.pos) : rewardProduct(this.pos);
        switch (card.type) {
            case "POINTS":
                if (!(card.points > 0 && card.pointsPerUnit > 0)) {
                    return _t("No points to use yet.");
                }
                if (!(this.maxPointsValue > 0)) {
                    return _t("Nothing on the order to take off.");
                }
                break;
            case "PREPAID":
                if (!(card.balance > 0)) {
                    return _t("No credit left on this card.");
                }
                if (!(this.due > 0)) {
                    return _t("Nothing left to pay.");
                }
                break;
            case "PACK":
                if (!((card.usesLeft || card.packUses) > 0)) {
                    return _t("No uses left on this pack.");
                }
                break;
            case "STAMPS":
                if (!card.rewardReady) {
                    return _t("Reward not ready yet.");
                }
                break;
            default:
                if (!((card.voucher?.usesLeft ?? 0) > 0)) {
                    return _t("This voucher is used up.");
                }
        }
        if (!ready) {
            return cantAddLine();
        }
        if (card.type !== "POINTS" && card.type !== "PREPAID" && !this.coverable.length) {
            return _t("Add the item it covers to the order first.");
        }
        return "";
    }

    useOf(card) {
        return { PACK: "pack", STAMPS: "reward", VOUCHER: "voucher" }[card.type];
    }

    /** What this card already put on the order: { label, remove } or null. */
    applied(card) {
        if (card.type === "PREPAID") {
            const payment = creditPayment(this.order);
            return payment
                ? {
                      label: _t("Paying %(amount)s with credit", { amount: this.money(payment.getAmount()) }),
                      remove: () => this.order.removePaymentline(payment),
                  }
                : null;
        }
        if (card.type === "POINTS") {
            const lines = pointsLines(this.order);
            if (!lines.length) {
                return null;
            }
            const value = lines.reduce((sum, line) => sum + Math.abs(line.priceIncl), 0);
            const points = lines.reduce((sum, line) => sum + (line.nuqtapass_qty || 0), 0);
            return {
                label: _t("On this order: %(value)s off · %(points)s points", {
                    value: this.money(value),
                    points: formatNumber(points),
                }),
                remove: () => lines.forEach((line) => this.order.removeOrderline(line)),
            };
        }
        const line = lineFor(this.order, this.useOf(card), card.type === "VOUCHER" ? card.cardId : null);
        if (!line) {
            return null;
        }
        const off = this.money(Math.abs(line.priceIncl));
        const label = _t("On this order: %(line)s · %(value)s off", { line: line.full_product_name, value: off });
        return { label, remove: () => this.order.removeOrderline(line) };
    }

    // points
    get maxPointsValue() {
        return totalWithoutPoints(this.order);
    }

    async usePoints(card, plan) {
        await setPointsLine(this.pos, this.order, card, plan);
    }

    // credit
    get due() {
        const payment = creditPayment(this.order);
        return Math.max(0, this.order.remainingDue + (payment ? payment.getAmount() : 0));
    }

    creditStart(card) {
        return creditAmount({ amount: card.balance, balance: card.balance, due: this.due, decimals: this.decimals });
    }

    /** The credit box: the amount due (up to the balance) until the cashier types in it. */
    creditText(card) {
        return boxText(this.state.credit, this.creditStart(card), this.decimals);
    }

    onCreditInput(ev) {
        this.state.credit = ev.target.value;
    }

    creditToUse(card) {
        return creditAmount({
            amount: parseMoney(this.creditText(card)),
            balance: card.balance,
            due: this.due,
            decimals: this.decimals,
        });
    }

    useCredit(card) {
        const amount = this.creditToUse(card);
        if (amount > 0) {
            setCreditPayment(this.pos, this.order, card, amount);
        }
    }

    // pack, stamp reward, voucher: the item it makes free
    get coverable() {
        return coverableLines(this.order);
    }

    itemLabel(line) {
        return `${line.getFullProductName?.() || line.full_product_name} · ${this.money(line.priceIncl / line.qty)}`;
    }

    picked(card) {
        const uuid = this.state.pick[card.cardId];
        return this.coverable.find((line) => line.uuid === uuid) || this.coverable[0] || null;
    }

    pick(card, uuid) {
        this.state.pick[card.cardId] = uuid;
    }

    useLabel(card) {
        return { PACK: _t("Use pack"), STAMPS: _t("Give it free"), VOUCHER: _t("Use voucher") }[card.type];
    }

    /** The free item's line, never taking the order below 0: a second free line on the same item is refused, and
     * points worth more than what is left are lowered (with a notice). */
    async useOnItem(card) {
        const use = this.useOf(card);
        const covered = this.picked(card);
        this.state.error = "";
        this.state.errorDetail = "";
        this.state.notice = "";
        if (covered && !freeLineFits(this.pos, this.order, use, covered, card.cardId)) {
            this.state.error = _t("This item is already free on this order: there is nothing left for it to make free.");
            return;
        }
        if (!(await setFreeLine(this.pos, this.order, card, use, covered))) {
            return;
        }
        const pointsCardId = pointsLines(this.order)[0]?.nuqtapass_card_id;
        const pointsCard = this.cards.find((c) => c.type === "POINTS" && c.cardId === pointsCardId);
        const plan = await fitPointsLine(this.pos, this.order, pointsCard, this.decimals);
        if (plan) {
            this.state.notice = plan.points
                ? _t("Points lowered to %(points)s (%(value)s off) so the order doesn't go below 0.", {
                      points: formatNumber(plan.points),
                      value: this.money(plan.value),
                  })
                : _t("Points removed: the free item leaves nothing on the order for them to take off.");
        }
    }
}

patch(PaymentScreen, {
    components: { ...PaymentScreen.components, NuqtaPassPayPanel },
});

patch(PaymentScreen.prototype, {
    /** "NuqtaPass credit" shows with the till's other methods (finance sees what each payment was), but never adds a
     * plain line: like the panel's "Use credit", it takes the looked-up customer's credit card, the amount due up to
     * its balance (editable on the numpad), and Validate spends it at NuqtaPass. A refund pays it back as usual. */
    async addNewPaymentLine(paymentMethod, args = {}) {
        if (!paymentMethod.nuqtapass_credit || this.isRefundOrder) {
            return super.addNewPaymentLine(paymentMethod, args);
        }
        const order = this.currentOrder;
        const pick = creditPick({
            cards: order.uiState?.nuqtapassCards || null,
            remainingDue: order.remainingDue,
            creditPaid: creditPayment(order)?.getAmount() || 0,
            decimals: order.uiState?.nuqtapassDecimals ?? this.pos.currency.decimal_places,
        });
        if (!pick.ok) {
            const body = {
                customer: _t("Look the customer up in the NuqtaPass panel first: the credit is taken from their card."),
                no_credit: _t("This customer has no NuqtaPass credit."),
                nothing_due: _t("Nothing left to pay."),
            }[pick.reason];
            this.dialog.add(AlertDialog, { title: _t("NuqtaPass"), body });
            return false;
        }
        const payment = setCreditPayment(this.pos, order, pick.card, pick.amount);
        if (!payment) {
            this.dialog.add(AlertDialog, { title: _t("NuqtaPass"), body: cantAddLine() });
            return false;
        }
        this.numberBuffer.set(payment.getAmount().toString());
        return true;
    },

    get nuqtapassPanel() {
        return Boolean(this.pos.config.nuqtapass_till_on && this.currentOrder && !this.isRefundOrder);
    },
});
