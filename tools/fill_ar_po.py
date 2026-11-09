"""Write <module>/i18n/ar.po from <module>/i18n/<module>.pot and tools/ar_terms.py. Runs inside the Odoo container (polib).

usage: python3 /mnt/extra-addons/tools/fill_ar_po.py <module> [<module> ...]
Exit 1 and list them if any msgid has no Arabic, so nothing ships half-translated.
"""
import os
import re
import sys

import polib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from ar_terms import TERMS  # noqa: E402

PLACEHOLDER = re.compile(r"%\(\w+\)s|%s")


def fill(module):
    pot = polib.pofile(os.path.join(ROOT, module, "i18n", f"{module}.pot"))
    po = polib.POFile(wrapwidth=pot.wrapwidth)
    po.metadata = dict(pot.metadata, Language="ar", **{"Plural-Forms": "nplurals=6; plural=n==0 ? 0 : n==1 ? 1 : "
                                                                          "n==2 ? 2 : n%100>=3 && n%100<=10 ? 3 : "
                                                                          "n%100>=11 ? 4 : 5;"})
    po.header = pot.header
    missing = []
    for entry in pot:
        arabic = TERMS.get(entry.msgid.strip())
        if arabic is None:
            missing.append(entry.msgid)
            continue
        if sorted(PLACEHOLDER.findall(entry.msgid)) != sorted(PLACEHOLDER.findall(arabic)):
            sys.exit(f"Placeholder mismatch for: {entry.msgid}")
        po.append(polib.POEntry(msgid=entry.msgid, msgstr=arabic, occurrences=entry.occurrences,
                                comment=entry.comment, tcomment=entry.tcomment, flags=entry.flags))
    if missing:
        print(f"{module}: no Arabic for:\n  " + "\n  ".join(missing))
        return False
    po.save(os.path.join(ROOT, module, "i18n", "ar.po"))
    print(f"{module}: filled {len(po)} entries")
    return True


if __name__ == "__main__":
    results = [fill(m) for m in sys.argv[1:]]
    sys.exit(0 if all(results) else 1)
