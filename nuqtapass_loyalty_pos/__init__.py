from . import controllers
from . import models


def post_init_hook(env):
    # The reward product is made when a till opens (pos.config.open_ui): here, modules this one doesn't depend on
    # may not be loaded yet.
    env["pos.payment.method"]._nuqtapass_ensure_all()
