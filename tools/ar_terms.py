"""English source → natural Gulf Arabic, in NuqtaPass's own words. The brand stays Latin ("NuqtaPass").

Same terms as the NuqtaPass staff app (apps/staff/src/pages/odooCopy.ts, lib/odoo.ts): الكاشير، المتجر الإلكتروني،
مرتجع، الربط، ختم/أختام، نقاط، مكافأة، قسيمة، انعطت/رجعت، ما فيه، مو.

Rules:
- Placeholders like %(n)s and %(shop)s stay unchanged (tools/fill_ar_po.py and the tests check).
- Numbers go after a label ("الأختام: %(stamps)s من %(required)s"), so every count reads right without plural forms.
- Never glue an Arabic prefix to a Latin word ("لـ NuqtaPass"): it breaks apart in RTL. Use "إلى NuqtaPass".
- Settings paths use "←" (RTL), quotes use «».
- Odoo's own generic terms (model names, Display Name, Close, Loading…) reuse Odoo's own Arabic, because a module's
  .po for an inherited model would overwrite Odoo's translation.
"""

# Odoo's own Arabic (read from the odoo:20.0 image's i18n/ar.po files), kept as is.
ODOO = {
    "Config Settings": "تهيئة الإعدادات",
    "Display Name": "اسم العرض",
    "ID": "المُعرف",
    "Created by": "أنشئ بواسطة",
    "Created on": "أنشئ في",
    "Last Updated by": "آخر تحديث بواسطة",
    "Last Updated on": "آخر تحديث في",
    "Journal Entry": "قيد اليومية",
    "Sales Order": "أمر البيع",
    "Website": "الموقع الإلكتروني",
    "Point of Sale Order": "طلب نقطة البيع",
    "Point of Sale Orders": "طلبات نقطة البيع",  # the same label in Odoo 19
    "Point of Sale Configuration": "تهيئة نقطة البيع",
    "Payment Transaction": "معاملة الدفع",
    "Company": "الشركة",
    "Currency": "العملة",
    "Close": "إغلاق",
    "Loading…": "جاري التحميل…",
}

TERMS = {
    **ODOO,
    # ── core: names, fields, choices ──────────────────────────────────
    "NuqtaPass": "NuqtaPass",
    "NuqtaPass Loyalty": "ولاء NuqtaPass",
    "Stamps and points on Apple Wallet and Google Wallet cards for every paid order":
        "أختام ونقاط على بطاقات Apple Wallet و Google Wallet مع كل طلب مدفوع",
    "NuqtaPass sync": "مزامنة NuqtaPass",
    "NuqtaPass sync log": "سجل مزامنة NuqtaPass",
    "Sale": "طلب",
    "Refund": "مرتجع",
    "Till": "الكاشير",
    "Online store": "المتجر الإلكتروني",
    "Waiting to send": "بانتظار الإرسال",
    "Sent": "انرسل",
    "Failed": "فشل",
    "Kind": "النوع",
    "Channel": "القناة",
    "State": "الحالة",
    "Order": "الطلب",
    "Phone": "الجوال",
    "Amount": "المبلغ",
    "Branch": "الفرع",
    "Customer Name": "اسم العميل",
    "Paid / refunded at": "وقت الدفع أو الإرجاع",
    "Phone looks wrong": "رقم الجوال شكله غلط",
    "Not a valid mobile number for its country, so it is not sent. Fix the phone and press Resend.":
        "هذا مو رقم جوال صحيح لبلده، فما ينرسل. صحّح الرقم واضغط «أعد الإرسال».",
    "Attempts": "المحاولات",
    "Next try": "المحاولة الجاية",
    "Last Error": "آخر خطأ",
    "Last Status Code": "آخر رمز حالة",
    "Dedupe Key": "مفتاح منع التكرار",
    "NuqtaPass answer": "رد NuqtaPass",
    "This order or refund is already queued for NuqtaPass.":
        "هالطلب أو المرتجع موجود من قبل في قائمة الإرسال إلى NuqtaPass.",
    "NuqtaPass: send orders and refunds": "NuqtaPass: إرسال الطلبات والمرتجعات",
    # ── core: status text (the NuqtaPass column and tab) ──────────────
    "No NuqtaPass key in Settings": "ما فيه مفتاح NuqtaPass في الإعدادات",
    "NuqtaPass is still working on this order": "NuqtaPass للحين يشتغل على هالطلب",
    "Failed: %(error)s": "فشل: %(error)s",
    "unknown error": "خطأ غير معروف",
    "Will try again: %(error)s": "بنحاول مرة ثانية: %(error)s",
    "Stamps given: %(n)s": "الأختام اللي انعطت: %(n)s",
    "Points given: %(n)s": "النقاط اللي انعطت: %(n)s",
    "Sent, nothing to give for this card": "انرسل، وما فيه شي ينعطى لهالبطاقة",
    "Stamps taken back: %(n)s": "الأختام اللي رجعت: %(n)s",
    "Points taken back: %(n)s": "النقاط اللي رجعت: %(n)s",
    "Stamps already used, not taken back: %(n)s": "أختام ما رجعت لأنها انستخدمت في مكافأة: %(n)s",
    "Points already used, not taken back: %(n)s": "نقاط ما رجعت لأنها انصرفت: %(n)s",
    "Sent, nothing to take back": "انرسل، وما فيه شي يرجع",
    "(NuqtaPass already had it)": "(وصل NuqtaPass من قبل)",
    # ── core: settings ────────────────────────────────────────────────
    "Connection": "الربط",
    "NuqtaPass key": "مفتاح NuqtaPass",
    "sip_…": "sip_…",
    "Create it on nuqtapass.com: Settings → Integrations → Odoo. It is shown once.":
        "سوّ المفتاح في nuqtapass.com من الإعدادات ← الربط ← Odoo. يطلع مرة وحدة بس، فانسخه على طول.",
    "Test connection": "جرّب الربط",
    "Earning": "الأختام والنقاط",
    "Earn at the till": "أختام ونقاط من الكاشير",
    "Paid till orders with a customer phone earn stamps or points.":
        "طلبات الكاشير المدفوعة اللي فيها جوال العميل تعطي أختام أو نقاط.",
    "Earn in the online store": "أختام ونقاط من المتجر الإلكتروني",
    "Paid online orders earn stamps or points.": "طلبات المتجر الإلكتروني المدفوعة تعطي أختام أو نقاط.",
    "Sync log": "سجل المزامنة",
    "Every order and refund sent to NuqtaPass.": "كل طلب ومرتجع انرسل إلى NuqtaPass.",
    "Open sync log": "افتح سجل المزامنة",
    "Paste your NuqtaPass key first.": "الصق مفتاح NuqtaPass أول.",
    "Could not connect: the NuqtaPass address setting is wrong.":
        "ما قدرنا نربط: عنوان NuqtaPass في الإعدادات مو صحيح.",
    "Connected to %(shop)s.": "تم الربط مع: %(shop)s",
    "Could not connect: %(error)s": "ما قدرنا نربط: %(error)s",
    # ── core: the sync log ────────────────────────────────────────────
    "Nothing sent yet": "ما انرسل شي للحين",
    "Paid orders with a customer phone show up here when they are sent to NuqtaPass.":
        "الطلبات المدفوعة اللي فيها جوال العميل تطلع هنا أول ما تنرسل إلى NuqtaPass.",
    "Resend": "أعد الإرسال",
    "Waiting": "بالانتظار",
    # ── till: back office ─────────────────────────────────────────────
    "NuqtaPass Loyalty – Point of Sale": "ولاء NuqtaPass – نقاط البيع",
    "Earn NuqtaPass stamps and points at the Odoo till, with a NuqtaPass button for rewards":
        "أختام ونقاط NuqtaPass من كاشير Odoo، مع زر NuqtaPass للمكافآت",
    "NuqtaPass branch": "فرع NuqtaPass",
    "Branch id, code or name in NuqtaPass. Empty: NuqtaPass tags the visit 'Odoo'.":
        "رقم الفرع أو رمزه أو اسمه في NuqtaPass. إذا خليته فاضي، الزيارة تنحسب على «Odoo».",
    "Which NuqtaPass branch this till's visits count for. Leave empty for 'Odoo'.":
        "أي فرع في NuqtaPass تنحسب له زيارات هالكاشير. خلّه فاضي عشان تنحسب على «Odoo».",
    "e.g. Qurum": "مثلاً: القرم",
    "NuqtaPass phone": "جوال NuqtaPass",
    "Phone typed in the NuqtaPass window on the till; used before the customer's own phone.":
        "الجوال اللي انكتب في نافذة NuqtaPass في الكاشير، وينستخدم قبل جوال العميل نفسه.",
    "Till order": "طلب الكاشير",
    # ── till: answers from the server ─────────────────────────────────
    "NuqtaPass is turned off for the till in Settings.": "NuqtaPass موقّف للكاشير في الإعدادات.",
    "Phone number looks wrong: %(phone)s": "رقم الجوال شكله غلط: %(phone)s",
    "Add your NuqtaPass key in Settings first.": "حط مفتاح NuqtaPass في الإعدادات أول.",
    "NuqtaPass can't be reached right now. The sale is saved and will earn when the connection is back.":
        "ما قدرنا نوصل إلى NuqtaPass الحين. الطلب محفوظ، وبتنعطى الأختام أو النقاط أول ما يرجع الاتصال.",
    "Odoo comes with the NuqtaPass Business plan. Ask the shop owner to upgrade on nuqtapass.com.":
        "ربط Odoo يجي مع باقة الأعمال في NuqtaPass. كلّم صاحب المحل يرقّي الباقة من nuqtapass.com.",
    "The shop's NuqtaPass plan has ended. The owner can renew it on nuqtapass.com.":
        "انتهى اشتراك المحل في NuqtaPass. صاحب المحل يقدر يجدده من nuqtapass.com.",
    "NuqtaPass refused the key. Check it in Settings.": "NuqtaPass رفض المفتاح. تأكد منه في الإعدادات.",
    "No NuqtaPass card for this phone yet.": "ما فيه بطاقة NuqtaPass لهالرقم للحين.",
    "NuqtaPass said no.": "NuqtaPass رفض الطلب.",
    "Something is missing. Look the customer up again.": "فيه شي ناقص. دوّر على العميل مرة ثانية.",
    "Reward given.": "انعطت المكافأة.",
    "Points used.": "انصرفت النقاط.",
    "Voucher used.": "انستخدمت القسيمة.",
    "Only Point of Sale users can use NuqtaPass on the till.":
        "بس مستخدمين نقاط البيع يقدرون يستخدمون NuqtaPass في الكاشير.",
    "This point of sale no longer exists.": "نقطة البيع هذي ما عادت موجودة.",
    # ── till: the NuqtaPass window ────────────────────────────────────
    "Customer phone": "جوال العميل",
    "Look up": "دوّر",
    "No card yet. The customer gets one with their first purchase.":
        "ما عنده بطاقة للحين. بتوصله وحدة مع أول شراء.",
    "Stamp card": "بطاقة الأختام",
    "Points card": "بطاقة النقاط",
    "Prepaid card": "بطاقة الرصيد",
    "Service pack": "باقة الخدمات",
    "Voucher": "قسيمة",
    "%(stamps)s of %(required)s stamps": "الأختام: %(stamps)s من %(required)s",
    "1 point": "نقطة وحدة",
    "%(points)s points": "النقاط: %(points)s",
    "Balance: %(balance)s": "الرصيد: %(balance)s",
    "1 use left": "باقي استخدام واحد",
    "%(uses)s uses left": "الاستخدامات الباقية: %(uses)s",
    "Give reward": "عطه المكافأة",
    "Points to use": "النقاط اللي بتنصرف",
    "Use points": "اصرف النقاط",
    "Use voucher": "استخدم القسيمة",
    "Type how many points to use, as a whole number.": "اكتب كم نقطة بتنصرف، رقم صحيح بدون كسور.",
    "Earn on this order": "احسبها على هالطلب",
    "QR code of the card": "كود QR للبطاقة",
    "Scan to add your card": "امسح الكود عشان تضيف بطاقتك",
    "Send by WhatsApp": "أرسلها على واتساب",
    "Send by SMS": "أرسلها برسالة SMS",
    # ── till: the simpler window, the receipt-screen box, Wallet card scans ─
    "NuqtaPass on the till": "NuqtaPass في الكاشير",
    "Phone or scan card": "رقم الجوال أو امسح البطاقة",
    "Find": "دوّر",
    "Add": "أضف",
    "Earn NuqtaPass points": "اجمع نقاط NuqtaPass",
    "This order will earn points": "هالطلب بيعطي نقاط",
    "This order will earn stamps": "هالطلب بيعطي أختام",
    "This order will earn for this customer": "هالطلب بينحسب لهالعميل",
    "1 point (%(value)s)": "نقطة وحدة (%(value)s)",
    "%(points)s points (%(value)s)": "النقاط: %(points)s (%(value)s)",
    "+1 point": "النقاط: +1",
    "+%(points)s points": "النقاط: +%(points)s",
    "+1 stamp": "الأختام: +1",
    "+%(stamps)s stamps": "الأختام: +%(stamps)s",
    "%(earned)s · %(total)s now": "%(earned)s · صارت %(total)s",
    "%(earned)s · %(stamps)s of %(required)s now": "%(earned)s · صارت %(stamps)s من %(required)s",
    "Sent. Nothing to earn on this card for this order.": "انرسل، وما فيه شي ينحسب لهالبطاقة على هالطلب.",
    "Saved. The order will earn when NuqtaPass can be reached.":
        "انحفظ. الطلب بينحسب أول ما يرجع الاتصال مع NuqtaPass.",
    "This card isn't from this shop.": "هالبطاقة مو من هالمحل.",
    "This order can't earn NuqtaPass points.": "هالطلب ما ينحسب له نقاط NuqtaPass.",
    "This order already earns for %(phone)s.": "هالطلب محسوب من قبل على الرقم: %(phone)s",
    # ── online store ──────────────────────────────────────────────────
    "NuqtaPass Loyalty – eCommerce": "ولاء NuqtaPass – المتجر الإلكتروني",
    "Earn NuqtaPass stamps and points on paid Odoo online-store orders; credit notes take them back":
        "أختام ونقاط NuqtaPass على طلبات متجر Odoo الإلكتروني المدفوعة، والإشعارات الدائنة ترجّعها",
    "NuqtaPass branch (online store)": "فرع NuqtaPass (المتجر الإلكتروني)",
    "Branch id, code or name in NuqtaPass. Empty: NuqtaPass tags the visit 'Odoo online'.":
        "رقم الفرع أو رمزه أو اسمه في NuqtaPass. إذا خليته فاضي، الطلب ينحسب على «Odoo online».",
    "Which NuqtaPass branch this website's orders count for. Leave empty for 'Odoo online'.":
        "أي فرع في NuqtaPass تنحسب له طلبات هالموقع. خلّه فاضي عشان تنحسب على «Odoo online».",
    "e.g. Online": "مثلاً: أونلاين",
    "Online order": "طلب المتجر الإلكتروني",
    "Credit note": "إشعار دائن",
    "NuqtaPass: find online orders paid by invoice": "NuqtaPass: دوّر على طلبات المتجر الإلكتروني المدفوعة بفاتورة",
}
