import { Component, useState } from "@odoo/owl";
import { correctionBody, REASON_MAX } from "./correction";

/**
 * A POS manager's correction on one card, inside its strip in the NuqtaPass window: undo the last stamp or add one
 * (stamp card), or points ± (points card), always with a reason. Saving calls `onSave` with the /adjust body.
 */
export class NuqtaPassCorrectBox extends Component {
    static template = "nuqtapass_loyalty_pos.CorrectBox";
    // Odoo 19 (OWL 2): static props, useState (20.0 uses useProps / proxy).
    static props = {
        card: Object,
        busy: { type: Boolean, optional: true },
        onSave: Function,
        onCancel: Function,
    };

    setup() {
        this.reasonMax = REASON_MAX;
        this.state = useState({
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
