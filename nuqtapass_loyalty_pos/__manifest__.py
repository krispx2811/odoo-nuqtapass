{
    "name": "NuqtaPass Loyalty – Point of Sale",
    "version": "19.0.1.0.0",
    "summary": "Earn NuqtaPass stamps and points at the Odoo till, with a NuqtaPass button for rewards",
    "category": "Sales/Point of Sale",
    "author": "NuqtaPass",
    "website": "https://nuqtapass.com",
    "license": "LGPL-3",
    "depends": ["nuqtapass_loyalty", "point_of_sale"],
    "data": [
        "views/pos_order_views.xml",
        "views/pos_config_views.xml",
        "views/nuqtapass_sync_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "nuqtapass_loyalty_pos/static/src/**/*",
        ],
    },
    "auto_install": True,
    "installable": True,
}
