from odoo import models


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    def _post_process(self):
        result = super()._post_process()
        # By now `sale` has confirmed the quotation of a done transaction.
        self.filtered(lambda tx: tx.state == "done").sale_order_ids._nuqtapass_queue_sale()
        return result
