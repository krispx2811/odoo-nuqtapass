from odoo import fields


def post_init_hook(env):
    # Orders paid before install never earn (no surprise back-fill). Odoo 20: typed set_str.
    env["ir.config_parameter"].sudo().set_str(
        "nuqtapass_loyalty_website_sale.since", fields.Datetime.to_string(fields.Datetime.now()))
