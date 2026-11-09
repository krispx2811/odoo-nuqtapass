import { Component, useProps, proxy, t } from "@odoo/owl";
import { correctionBody, REASON_MAX } from "./correction";

/**
 * A POS manager's correction on one card, inside its strip in the NuqtaPass window: undo the last stamp or add one
 * (stamp card), or points ± (points card), always with a reason. Saving calls `onSave` with the /adjust body.
 */
export class NuqtaPassCorrectBox extends Component {
    static template = "nuqtapass_loyalty_pos.CorrectBox";
    props = useProps({
        card: t.object(),
        busy: t.boolean().optional(false),
        onSave: t.function(),
        onCancel: t.function(),
    });

    setup() {
        this.reasonMax = REASON_MAX;
        this.state = proxy({
            action: this.props.card.type === "POINTS" ? "points" : "stamp_undo",
            points: "",
            reason: "",
        });
    }

    get isStamps() {
        return this.props.card.type === "STAMPS";
    }

    get id() {
        return this.props.card.cardId;
    }

    get check() {
        return correctionBody(this.props.card, this.state);
    }

    pick(action) {
        this.state.action = action;
    }

    save() {
        const check = this.check;
        if (check.ok && !this.props.busy) {
            this.props.onSave(check.body);
        }
    }
}
