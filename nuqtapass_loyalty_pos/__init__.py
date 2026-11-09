from . import controllers
from . import models


def post_init_hook(env):
    env["pos.payment.method"]._nuqtapass_ensure_all()
