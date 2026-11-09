from odoo import http
from odoo.exceptions import AccessError, MissingError
from odoo.http import request


class NuqtaPassPosController(http.Controller):
    """The till's NuqtaPass window calls these. The NuqtaPass key stays on the server."""

    def _config(self, config_id):
        if not request.env.user.has_group("point_of_sale.group_pos_user"):
            raise AccessError(request.env._("Only Point of Sale users can use NuqtaPass on the till."))
        config = request.env["pos.config"].browse(int(config_id)).exists()
        if not config:
            raise MissingError(request.env._("This point of sale no longer exists."))
        config.check_access("read")
        return config

    @http.route("/nuqtapass_loyalty/pos/customer", type="jsonrpc", auth="user", methods=["POST"])
    def customer(self, config_id, phone):
        return self._config(config_id)._nuqtapass_lookup(phone)

    @http.route("/nuqtapass_loyalty/pos/redeem", type="jsonrpc", auth="user", methods=["POST"])
    def redeem(self, config_id, phone, card_id, action, voucher_id=None, points=None):
        return self._config(config_id)._nuqtapass_redeem(phone, card_id, action, voucher_id, points)

    @http.route("/nuqtapass_loyalty/pos/after_payment", type="jsonrpc", auth="user", methods=["POST"])
    def after_payment(self, config_id, order_id):
        return self._config(config_id)._nuqtapass_after_payment(order_id)
