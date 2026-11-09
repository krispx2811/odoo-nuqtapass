"""The Arabic files: complete, placeholders intact, and actually shown to Arabic users."""
import os
import re

import polib

from odoo.modules.module import get_module_path
from odoo.tests import TransactionCase, tagged

MODULES = ("nuqtapass_loyalty", "nuqtapass_loyalty_pos", "nuqtapass_loyalty_website_sale")
PLACEHOLDER = re.compile(r"%\(\w+\)s|%s|\{\{.*?\}\}")
# Arabic prefixes glued to a Latin word ("لـ NuqtaPass") break apart in RTL (arabic-design rule 4).
GLUED_PREFIX = re.compile(r"(?:^|\s)(?:الـ|بالـ|للـ|لـ|بـ)\s?[A-Za-z]")


def _po(module, name):
    path = os.path.join(get_module_path(module), "i18n", name)
    return polib.pofile(path) if os.path.exists(path) else None


@tagged("post_install", "-at_install", "nuqtapass")
class TestArabicFiles(TransactionCase):
    def test_every_module_has_a_template_and_arabic(self):
        for module in MODULES:
            with self.subTest(module=module):
                self.assertIsNotNone(_po(module, f"{module}.pot"), "missing .pot")
                self.assertIsNotNone(_po(module, "ar.po"), "missing ar.po")

    def test_arabic_covers_the_template(self):
        for module in MODULES:
            pot, po = _po(module, f"{module}.pot"), _po(module, "ar.po")
            if not (pot and po):
                self.fail(f"{module}: missing i18n files")
            arabic = {e.msgid: e.msgstr for e in po}
            for entry in pot:
                with self.subTest(module=module, msgid=entry.msgid):
                    self.assertTrue(arabic.get(entry.msgid), "no Arabic")

    def test_placeholders_kept_and_no_glued_prefix(self):
        for module in MODULES:
            po = _po(module, "ar.po")
            if not po:
                self.fail(f"{module}: missing ar.po")
            for entry in po:
                with self.subTest(module=module, msgid=entry.msgid):
                    self.assertEqual(sorted(PLACEHOLDER.findall(entry.msgid)), sorted(PLACEHOLDER.findall(entry.msgstr)))
                    self.assertFalse(GLUED_PREFIX.search(entry.msgstr), entry.msgstr)


@tagged("post_install", "-at_install", "nuqtapass")
class TestArabicShown(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["res.lang"]._activate_lang("ar_001")
        cls.env["ir.module.module"]._load_module_terms(["nuqtapass_loyalty"], ["ar_001"], overwrite=True)
        cls.ar = cls.env(context=dict(cls.env.context, lang="ar_001"))

    def test_status_text_in_arabic(self):
        Sync = self.ar["nuqtapass.sync"].sudo()
        rec = Sync.create({"kind": "sale", "channel": "till", "order_ref": "R1", "dedupe_key": "sale|R1|",
                           "occurred_at": "2026-11-09 10:00:00", "state": "done",
                           "response_json": '{"result": {"stamps": 1}}'})
        self.assertEqual(rec.summary, "الأختام اللي انعطت: 1")

    def test_settings_labels_in_arabic(self):
        arch = self.ar["res.config.settings"].get_view(view_type="form")["arch"]
        self.assertIn("مفتاح NuqtaPass", arch)

    def test_wrong_phone_in_arabic(self):
        rec = self.ar["nuqtapass.sync"].sudo().create({
            "kind": "sale", "channel": "till", "order_ref": "R2", "dedupe_key": "sale|R2|", "phone": "9417872",
            "occurred_at": "2026-11-09 10:00:00", "state": "failed", "phone_invalid": True})
        self.assertEqual(rec.summary, "رقم الجوال شكله غلط: 9417872")
