import { Component, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { user } from "@web/core/user";
import { money } from "../nuqtapass_api";
import { formatMoney, formatNumber, parseMoney, planPoints, startingAmount } from "./nuqtapass_math";

/**
 * Points as money: the cashier types an amount in NuqtaPass's currency and sees the points it takes, live
 * ("= 167 points"). The discount is the value of those whole points, never more than the order's total.
 */
export class NuqtaPassPointsBox extends Component {
    static template = "nuqtapass_loyalty_pos.PointsBox";
    // Odoo 19 (OWL 2): static props, useState (20.0 uses useProps / proxy).
    static props = {
        card: Object,
        currency: { type: [Object, { value: null }], optional: true },
        // The shop's per-visit cap ({value, points}) or null.
        cap: { type: [Object, { value: null }], optional: true },
        // The order's total before its points line: the most the points can take off.
        maxValue: Number,
        busy: { type: Boolean, optional: true },
        onUse: Function,
    };

    setup() {
        const decimals = this.decimals;
        this.state = useState({
            amount: startingAmount({
                orderTotal: this.props.maxValue,
                cardWorth: this.props.card.pointsValue,
                capValue: this.props.cap?.value ?? null,
                decimals,
            }).toFixed(decimals),
        });
    }

    get decimals() {
        return this.props.currency?.decimals ?? 3;
    }

    get inputId() {
        return `o_nuqtapass_amount_${this.props.card.cardId}`;
    }

    get currencyLabel() {
        return formatMoney(0, this.props.currency, user.lang).replace(/^[\d.,\s]+/, "");
    }

    get plan() {
        return planPoints({
            amount: parseMoney(this.state.amount),
            ppu: this.props.card.pointsPerUnit,
            decimals: this.decimals,
            cardPoints: this.props.card.points,
            capPoints: this.props.cap?.points ?? null,
            maxValue: this.props.maxValue,
        });
    }

    get liveLine() {
        const plan = this.plan;
        if (!plan.points) {
            return Number.isNaN(parseMoney(this.state.amount))
                ? _t("Type an amount")
                : _t("Nothing to take off");
        }
        const points = formatNumber(plan.points);
        const line = plan.points === 1 ? _t("= 1 point") : _t("= %(points)s points", { points });
        // Whole points: always say what comes off (it can differ from what was typed by part of one point).
        return _t("%(points)s · %(value)s off", { points: line, value: money(plan.value, this.props.currency) });
    }

    /** Why less than what was typed comes off (the amount due, the card's worth or the per-visit limit), or "". */
    get cappedLine() {
        const capped = this.plan.capped;
        if (!capped) {
            return "";
        }
        const value = money(capped.value, this.props.currency);
        if (capped.reason === "due") {
            return _t("Capped at the amount due (%(value)s)", { value });
        }
        if (capped.reason === "card") {
            return _t("Capped at the card's worth (%(value)s)", { value });
        }
        return _t("Capped at the per-visit limit (%(value)s)", { value });
    }

    use() {
        const plan = this.plan;
        if (plan.points > 0) {
            this.props.onUse(plan);
        }
    }
}
