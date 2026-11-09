import glob
import os

from odoo.modules.module import get_module_path
from odoo.tests import TransactionCase, tagged

try:
    import sass  # libsass: what Odoo compiles the till's SCSS with
except ImportError:  # pragma: no cover
    sass = None


@tagged("post_install", "-at_install", "nuqtapass")
class TestPosAssets(TransactionCase):
    """A SCSS error breaks the whole till's styles ("Style error"), so every file must compile with libsass."""

    def test_scss_compiles(self):
        if sass is None:
            self.skipTest("libsass not installed")
        files = glob.glob(os.path.join(get_module_path("nuqtapass_loyalty_pos"), "static", "src", "**", "*.scss"),
                          recursive=True)
        self.assertTrue(files)
        for path in files:
            with self.subTest(path=os.path.basename(path)), open(path, encoding="utf-8") as handle:
                sass.compile(string=handle.read())
