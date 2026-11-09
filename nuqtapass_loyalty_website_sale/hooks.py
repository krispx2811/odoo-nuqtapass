from odoo import fields


def post_init_hook(env):
    # Orders paid before install never earn (no surprise back-fill). Odoo 19: set_param.
    env["ir.config_parameter"].sudo().set_param(
        "nuqtapass_loyalty_website_sale.since", fields.Datetime.to_string(fields.Datetime.now()))
