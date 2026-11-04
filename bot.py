"""
Telegram Bot Control Panel for A2 TV App.
Modern, streamlined, and high-performance control panel.
Provides full management for:
1. Categories (Unlimited scalability with Pagination & Search)
2. Channels inside Categories (Add, Edit, Delete, Qualities, Pagination)
3. App APK Updates (Upload APK, Direct URL, Force Update, Versioning)
4. Push Notifications (Broadcast title, text, banner image to app users)
5. Maintenance System (Instant ON/OFF, Custom message, Logo, Background color)
6. System Overview & Admin Permissions
"""

import os
import re
import json
import time
import telebot
from telebot import types
from datetime import datetime

from config import BOT_TOKEN, ADMIN_ID, API_HOST, API_PORT, PUBLIC_URL, APP_PACKAGE, CURRENT_APP_VERSION_CODE, logger
from database import db

# Initialize TeleBot
BOT_INITIALIZED = False
if BOT_TOKEN and ":" in BOT_TOKEN and BOT_TOKEN != "YOUR_TELEGRAM_BOT_TOKEN_HERE":
    try:
        bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
        BOT_INITIALIZED = True
    except Exception as e:
        logger.error("Failed to initialize TeleBot: %s", e)
        bot = telebot.TeleBot("123456789:AAFakeTokenForValidationPlaceholderUntilReal", parse_mode="HTML")
else:
    bot = telebot.TeleBot("123456789:AAFakeTokenForValidationPlaceholderUntilReal", parse_mode="HTML")

# Paths for uploaded assets
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
UPDATES_DIR = os.path.join(DATA_DIR, "updates")
UPLOADS_DIR = os.path.join(DATA_DIR, "uploads")
os.makedirs(UPDATES_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)

# State management for multi-step wizards
user_states = {}

def get_user_id(msg_or_call):
    if hasattr(msg_or_call, "from_user") and msg_or_call.from_user:
        return msg_or_call.from_user.id
    return msg_or_call.chat.id

def is_admin(user_id):
    return db.is_admin(user_id)

def cancel_keyboard():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("❌ إلغاء والعودة للرئيسية", callback_data="main_menu"))
    return kb

def back_keyboard(callback_target="main_menu"):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔙 رجوع", callback_data=callback_target))
    return kb

# ----------------- Keyboard Generators -----------------

def main_dashboard_keyboard(user_id):
    """Main Control Panel with the 6 core pillars."""
    kb = types.InlineKeyboardMarkup(row_width=2)
    b_cats = types.InlineKeyboardButton("🗂️ إدارة الأقسام", callback_data="cat_p_1")
    b_channels = types.InlineKeyboardButton("📺 إدارة القنوات", callback_data="ch_hub_0")
    b_updates = types.InlineKeyboardButton("🚀 تحديث التطبيق APK", callback_data="menu_update")
    b_notifs = types.InlineKeyboardButton("🔔 إرسال الإشعارات", callback_data="menu_notif")
    b_maint = types.InlineKeyboardButton("🛠️ نظام الصيانة", callback_data="menu_maint")
    b_stats = types.InlineKeyboardButton("📊 إحصائيات النظام", callback_data="menu_stats")

    kb.row(b_cats, b_channels)
    kb.row(b_updates, b_notifs)
    kb.row(b_maint, b_stats)

    if ADMIN_ID and int(user_id) == ADMIN_ID:
        kb.add(types.InlineKeyboardButton("👥 إدارة المشرفين", callback_data="menu_admins"))
    return kb

# ----------------- Command Handlers -----------------

@bot.message_handler(commands=['start', 'panel', 'admin', 'menu'])
def handle_start(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        text = (
            "⛔ <b>عذراً، هذه اللوحة مخصصة لإدارة تطبيق A2 TV فقط.</b>\n"
            f"معرفك الخاص: <code>{user_id}</code>\n"
            "تواصل مع الإدارة للحصول على الصلاحيات."
        )
        bot.send_message(message.chat.id, text)
        return

    user_states.pop(user_id, None)
    text = (
        "👋 <b>أهلاً بك في لوحة تحكم تطبيق A2 TV المحدثة</b> 🚀\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "تحكم شامل وفوري في الأقسام، القنوات، التحديثات، الإشعارات، ونظام الصيانة.\n"
        "اختر أحد الأقسام أدناه للبدء:"
    )
    bot.send_message(message.chat.id, text, reply_markup=main_dashboard_keyboard(user_id))

# ----------------- 1. Categories Management -----------------

def render_categories_page(page=1, search_query="", page_size=8):
    paged = db.get_categories_paged(page=page, page_size=page_size, search_query=search_query)
    cats = paged["items"]
    cur_page = paged["page"]
    total_pages = paged["total_pages"]
    total_items = paged["total_items"]

    kb = types.InlineKeyboardMarkup(row_width=2)
    # Action buttons
    kb.row(
        types.InlineKeyboardButton("➕ إنشاء قسم جديد", callback_data="cat_add"),
        types.InlineKeyboardButton("🔍 بحث عن قسم", callback_data="cat_search_prompt")
    )

    if search_query:
        kb.add(types.InlineKeyboardButton("❌ إلغاء البحث وعرض الكل", callback_data="cat_p_1"))

    # Categories list
    for c in cats:
        cid = c["id"]
        cname = c.get("name", cid)
        icon = c.get("icon", "📁")
        ch_count = len(db.get_channels(cid))
        hidden_mark = " [مخفي]" if c.get("hidden", False) else ""
        btn_text = f"{icon} {cname} ({ch_count} قناة){hidden_mark}"
        kb.add(types.InlineKeyboardButton(btn_text, callback_data=f"cat_view_{cid}"))

    # Pagination buttons
    nav_row = []
    if cur_page > 1:
        prev_call = f"cat_p_{cur_page - 1}" if not search_query else f"cat_s_{cur_page - 1}_{search_query}"
        nav_row.append(types.InlineKeyboardButton("➡️ السابق", callback_data=prev_call))
    nav_row.append(types.InlineKeyboardButton(f"📄 {cur_page} / {total_pages}", callback_data="noop"))
    if cur_page < total_pages:
        next_call = f"cat_p_{cur_page + 1}" if not search_query else f"cat_s_{cur_page + 1}_{search_query}"
        nav_row.append(types.InlineKeyboardButton("التالي ⬅️", callback_data=next_call))
    if len(nav_row) > 1:
        kb.row(*nav_row)

    kb.add(types.InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="main_menu"))

    search_status = f"\n🔍 نتيجة البحث عن: <b>«{search_query}»</b>" if search_query else ""
    text = (
        f"🗂️ <b>إدارة أقسام التطبيق</b>{search_status}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"إجمالي الأقسام: <b>{total_items}</b> قسم\n"
        f"الصفحة الحالية: <b>{cur_page} من {total_pages}</b>\n\n"
        f"اضغط على أي قسم لإدارته وتعديل شعاره أو عرض قنواته:"
    )
    return text, kb

# ----------------- 2. Channels Management -----------------

def render_channels_page(category_id="all", page=1, search_query="", page_size=8):
    cat_obj = db.get_category(category_id) if category_id != "all" else None
    cat_name = cat_obj.get("name", "جميع القنوات") if cat_obj else "جميع القنوات"

    paged = db.get_channels_by_category_paged(category_id=category_id, page=page, page_size=page_size, search_query=search_query)
    channels = paged["items"]
    cur_page = paged["page"]
    total_pages = paged["total_pages"]
    total_items = paged["total_items"]

    kb = types.InlineKeyboardMarkup(row_width=2)
    # Action buttons
    if category_id != "all":
        kb.row(
            types.InlineKeyboardButton("➕ إضافة قناة هنا", callback_data=f"ch_add_in_{category_id}"),
            types.InlineKeyboardButton("🔍 بحث بالقنوات", callback_data=f"ch_search_in_{category_id}")
        )
    else:
        kb.row(
            types.InlineKeyboardButton("📂 اختيار قسم لإضافة قناة", callback_data="cat_p_1"),
            types.InlineKeyboardButton("🔍 بحث عام بالقنوات", callback_data="ch_search_in_all")
        )

    if search_query:
        kb.add(types.InlineKeyboardButton("❌ إلغاء البحث", callback_data=f"ch_cat_{category_id}_1"))

    # Channel buttons
    for ch in channels:
        chid = ch["id"]
        chname = ch.get("name", "قناة بدون اسم")
        qual = ch.get("quality", "FHD")
        dis = " [معطلة ⛔]" if ch.get("disabled", False) else ""
        kb.add(types.InlineKeyboardButton(f"📺 {chname} ({qual}){dis}", callback_data=f"ch_view_{chid}"))

    # Pagination buttons
    nav_row = []
    if cur_page > 1:
        nav_row.append(types.InlineKeyboardButton("➡️ السابق", callback_data=f"ch_cat_{category_id}_{cur_page - 1}"))
    nav_row.append(types.InlineKeyboardButton(f"📄 {cur_page} / {total_pages}", callback_data="noop"))
    if cur_page < total_pages:
        nav_row.append(types.InlineKeyboardButton("التالي ⬅️", callback_data=f"ch_cat_{category_id}_{cur_page + 1}"))
    if len(nav_row) > 1:
        kb.row(*nav_row)

    if category_id != "all":
        kb.add(types.InlineKeyboardButton(f"📁 تفاصيل قسم «{cat_name}»", callback_data=f"cat_view_{category_id}"))
    kb.add(types.InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="main_menu"))

    search_status = f"\n🔍 نتيجة البحث عن: <b>«{search_query}»</b>" if search_query else ""
    text = (
        f"📺 <b>إدارة القنوات - {cat_name}</b>{search_status}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"إجمالي القنوات: <b>{total_items}</b> قناة\n"
        f"الصفحة: <b>{cur_page} من {total_pages}</b>\n\n"
        f"اضغط على أي قناة لتعديل اسمها، رابطها، أو جودتها:"
    )
    return text, kb

# ----------------- 3. App APK Updates -----------------

def render_update_menu():
    up = db.get_app_update()
    is_enabled = up.get("enabled", False)
    is_force = up.get("is_force", False)
    status_text = "🟢 مفعل ومتاح للمستخدمين" if is_enabled else "🔴 معطل حالياً"
    type_text = "🔴 إجباري (نافذة إجبارية لا يمكن تخطيها)" if is_force else "🟡 اختياري (يمكن تخطيه)"

    text = (
        "🚀 <b>لوحة تحديثات التطبيق (APK Update Manager)</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔘 حالة التحديث: <b>{status_text}</b>\n"
        f"⚠️ نوع التحديث: <b>{type_text}</b>\n"
        f"🔢 رقم الإصدار (Version Code): <code>{up.get('version_code', 1)}</code>\n"
        f"🏷️ اسم الإصدار (Version Name): <b>{up.get('version_name', '1.0')}</b>\n"
        f"🔗 رابط التحميل:\n<code>{up.get('download_url', 'غير محدد')}</code>\n\n"
        f"📝 <b>ملاحظات التحديث:</b>\n{up.get('release_notes', 'تحديث جديد لتطبيق A2 TV')}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "اختر أحد الإجراءات التالية:"
    )

    kb = types.InlineKeyboardMarkup(row_width=2)
    b_upload = types.InlineKeyboardButton("📤 رفع ملف APK مباشر", callback_data="up_upload_apk")
    b_url = types.InlineKeyboardButton("🔗 إدخال رابط تحميل مباشر", callback_data="up_set_url")
    b_version = types.InlineKeyboardButton("🔢 تحديد رقم الإصدار", callback_data="up_set_version")
    b_notes = types.InlineKeyboardButton("📝 تعديل الملاحظات", callback_data="up_set_notes")

    force_label = "🟡 جعله اختيارياً" if is_force else "🔴 تفعيل التحديث الإجباري"
    b_force = types.InlineKeyboardButton(force_label, callback_data="up_toggle_force")

    state_label = "⏸️ تعطيل التحديث" if is_enabled else "▶️ تفعيل التحديث الآن"
    b_toggle = types.InlineKeyboardButton(state_label, callback_data="up_toggle_state")

    b_broadcast = types.InlineKeyboardButton("📢 إرسال إشعار التحديث للمستخدمين", callback_data="up_broadcast")
    b_back = types.InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="main_menu")

    kb.row(b_upload, b_url)
    kb.row(b_version, b_notes)
    kb.row(b_force, b_toggle)
    kb.add(b_broadcast)
    kb.add(b_back)
    return text, kb

# ----------------- 4. Push Notifications -----------------

def render_notifications_menu():
    latest = db.get_latest_notification()
    last_text = "لا توجد إشعارات سابقة"
    if latest:
        img_badge = " [مرفق صورة 🖼️]" if latest.get("image") else ""
        last_text = (
            f"<b>{latest.get('title')}</b>{img_badge}\n"
            f"{latest.get('message')}\n"
            f"<i>التاريخ: {latest.get('created_at')}</i>"
        )

    text = (
        "🔔 <b>نظام الإشعارات الرياضية والشعارات</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "يمكنك إرسال إشعار فوري لجميع مستخدمي التطبيق مع إمكانية إرفاق شعار أو صورة مميزة.\n\n"
        f"📌 <b>آخر إشعار تم إرساله:</b>\n{last_text}\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )

    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("📢 إنشاء وإرسال إشعار جديد الآن", callback_data="notif_new"))
    kb.add(types.InlineKeyboardButton("📋 سجل الإشعارات السابقة", callback_data="notif_history"))
    kb.add(types.InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="main_menu"))
    return text, kb

# ----------------- 5. Maintenance System -----------------

def render_maintenance_menu():
    m = db.get_maintenance()
    is_active = m.get("enabled", False)
    status_badge = "🔴 وضع الصيانة مُفعل (التطبيق متوقف للمستخدمين)" if is_active else "🟢 وضع الصيانة مُعطل (التطبيق يعمل بشكل طبيعي)"

    logo_text = f"<code>{m.get('image')}</code>" if m.get("image") else "افتراضي (شعار التطبيق)"
    bg_text = f"<code>{m.get('bg_color', '#0F0A18')}</code>"

    text = (
        "🛠️ <b>نظام وضع الصيانة للتطبيق</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"الحالة: <b>{status_badge}</b>\n\n"
        f"💬 <b>رسالة الصيانة الحالية:</b>\n{m.get('message')}\n\n"
        f"🖼️ <b>شعار/صورة الصيانة:</b> {logo_text}\n"
        f"🎨 <b>لون الخلفية:</b> {bg_text}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "التحكم الفوري بوضع الصيانة:"
    )

    kb = types.InlineKeyboardMarkup(row_width=2)
    b_on = types.InlineKeyboardButton("🔴 تشغيل وضع الصيانة", callback_data="maint_enable")
    b_off = types.InlineKeyboardButton("🟢 إيقاف وضع الصيانة", callback_data="maint_disable")
    b_msg = types.InlineKeyboardButton("✏️ تعديل نص الرسالة", callback_data="maint_set_msg")
    b_logo = types.InlineKeyboardButton("🖼️ تغيير الشعار والصورة", callback_data="maint_set_logo")
    b_bg = types.InlineKeyboardButton("🎨 تغيير لون الخلفية", callback_data="maint_set_bg")
    b_back = types.InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="main_menu")

    kb.row(b_on, b_off)
    kb.row(b_msg, b_logo)
    kb.add(b_bg)
    kb.add(b_back)
    return text, kb

# ----------------- 6. System Stats -----------------

def render_stats_menu():
    channels = db.get_channels()
    categories = db.get_categories()
    m = db.get_maintenance()
    up = db.get_app_update()

    text = (
        "📊 <b>إحصائيات وحالة نظام A2 TV</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📁 إجمالي الأقسام: <b>{len(categories)}</b> قسم\n"
        f"📺 إجمالي القنوات المباشرة: <b>{len(channels)}</b> قناة\n"
        f"🛠️ حالة الصيانة: <b>{'🔴 قيد الصيانة' if m.get('enabled') else '🟢 يعمل بكفاءة'}</b>\n"
        f"🚀 التحديث الإجباري: <b>{'مفعل ✅' if up.get('enabled') and up.get('is_force') else 'معطل'}</b>\n"
        f"🌐 سيرفر الـ API: <code>{PUBLIC_URL}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔄 تحديث الإحصائيات", callback_data="menu_stats"))
    kb.add(types.InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="main_menu"))
    return text, kb

# ----------------- Callback Query Router -----------------

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    if not is_admin(user_id):
        bot.answer_callback_query(call.id, "⚠️ غير مصرح لك باستخدام هذه اللوحة!", show_alert=True)
        return

    data = call.data
    chat_id = call.message.chat.id
    msg_id = call.message.message_id

    # 1. Main Navigation
    if data == "main_menu":
        user_states.pop(user_id, None)
        text = (
            "👋 <b>لوحة تحكم A2 TV المركزية</b> 🚀\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "اختر القسم المطلوب لإدارته:"
        )
        try:
            bot.edit_message_text(text, chat_id, msg_id, reply_markup=main_dashboard_keyboard(user_id))
        except Exception:
            bot.send_message(chat_id, text, reply_markup=main_dashboard_keyboard(user_id))
        bot.answer_callback_query(call.id)
        return

    if data == "noop":
        bot.answer_callback_query(call.id)
        return

    # 2. Categories Routing
    if data.startswith("cat_p_"):
        page = int(data.split("_")[2])
        text, kb = render_categories_page(page=page)
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=kb)
        bot.answer_callback_query(call.id)
        return

    if data.startswith("cat_s_"):
        parts = data.split("_", 3)
        page = int(parts[2])
        q = parts[3]
        text, kb = render_categories_page(page=page, search_query=q)
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=kb)
        bot.answer_callback_query(call.id)
        return

    if data == "cat_search_prompt":
        user_states[user_id] = {"action": "wait_cat_search"}
        bot.edit_message_text("🔍 <b>أرسل الآن اسم القسم أو المعرف الذي تريد البحث عنه:</b>", chat_id, msg_id, reply_markup=cancel_keyboard())
        bot.answer_callback_query(call.id)
        return

    if data == "cat_add":
        user_states[user_id] = {"action": "wait_cat_name", "data": {}}
        prompt = (
            "📁 <b>إنشاء قسم جديد</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "<b>الخطوة 1 من 2:</b> أرسل الآن <b>اسم القسم الجديد</b> (مثال: قنوات وثائقية):"
        )
        bot.edit_message_text(prompt, chat_id, msg_id, reply_markup=cancel_keyboard())
        bot.answer_callback_query(call.id)
        return

    if data.startswith("cat_view_"):
        cid = data[len("cat_view_"):]
        c = db.get_category(cid)
        if not c:
            bot.answer_callback_query(call.id, "⚠️ القسم غير موجود", show_alert=True)
            return

        ch_in_cat = db.get_channels(cid)
        banner_info = f"🖼️ الشعار/البنر: <b>موجود ✅</b>\n" if c.get("image") else "🖼️ الشعار/البنر: <b>غير محدد</b>\n"
        status_text = "👁️ مخفي في التطبيق" if c.get("hidden", False) else "🟢 ظاهر في التطبيق"

        text = (
            f"📁 <b>إدارة القسم: {c.get('icon', '📁')} {c.get('name')}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🆔 المعرف البرمجي: <code>{cid}</code>\n"
            f"🔘 الحالة: <b>{status_text}</b>\n"
            f"🎨 الأيقونة: <b>{c.get('icon', '📁')}</b>\n"
            f"{banner_info}"
            f"📺 عدد القنوات بداخله: <b>{len(ch_in_cat)}</b> قناة\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "اختر الإجراء المطلوب:"
        )

        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.row(
            types.InlineKeyboardButton(f"📺 قنوات هذا القسم ({len(ch_in_cat)})", callback_data=f"ch_cat_{cid}_1"),
            types.InlineKeyboardButton("➕ إضافة قناة هنا", callback_data=f"ch_add_in_{cid}")
        )
        kb.row(
            types.InlineKeyboardButton("✏️ تعديل الاسم", callback_data=f"cat_edname_{cid}"),
            types.InlineKeyboardButton("🎨 تغيير الأيقونة والشعار", callback_data=f"cat_edicon_{cid}")
        )
        toggle_hide_label = "🟢 إظهار في التطبيق" if c.get("hidden", False) else "👁️ إخفاء من التطبيق"
        kb.row(
            types.InlineKeyboardButton(toggle_hide_label, callback_data=f"cat_toggle_{cid}"),
            types.InlineKeyboardButton("🗑️ حذف القسم", callback_data=f"cat_del_{cid}")
        )
        kb.add(types.InlineKeyboardButton("🔙 رجوع لقائمة الأقسام", callback_data="cat_p_1"))

        bot.edit_message_text(text, chat_id, msg_id, reply_markup=kb)
        bot.answer_callback_query(call.id)
        return

    if data.startswith("cat_toggle_"):
        cid = data[len("cat_toggle_"):]
        ok, res = db.toggle_category_hidden(cid)
        bot.answer_callback_query(call.id, "تم تحديث حالة الظهور في التطبيق بنجاح ✅")
        call.data = f"cat_view_{cid}"
        handle_callbacks(call)
        return

    if data.startswith("cat_edname_"):
        cid = data[len("cat_edname_"):]
        user_states[user_id] = {"action": "wait_cat_new_name", "data": {"cid": cid}}
        bot.edit_message_text("✏️ <b>أرسل الآن الاسم الجديد للقسم:</b>", chat_id, msg_id, reply_markup=cancel_keyboard())
        bot.answer_callback_query(call.id)
        return

    if data.startswith("cat_edicon_"):
        cid = data[len("cat_edicon_"):]
        user_states[user_id] = {"action": "wait_cat_new_icon", "data": {"cid": cid}}
        text = (
            "🎨 <b>تغيير أيقونة وشعار القسم</b>\n"
            "أرسل الآن الإيموجي أو الأيقونة المطلوبة (مثل: ⚽، 🎬، 🕋)\n"
            "أو أرسل رابط صورة لشعار القسم أو ارفع الصورة مباشرة!"
        )
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=cancel_keyboard())
        bot.answer_callback_query(call.id)
        return

    if data.startswith("cat_del_"):
        cid = data[len("cat_del_"):]
        c = db.get_category(cid)
        ch_cnt = len(db.get_channels(cid))
        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.add(types.InlineKeyboardButton("🗑️ نعم، احذف القسم وقنواته معاً", callback_data=f"cat_del_confirm_{cid}_both"))
        kb.add(types.InlineKeyboardButton("📁 احذف القسم فقط وانقل قنواته لقسم عام", callback_data=f"cat_del_confirm_{cid}_move"))
        kb.add(types.InlineKeyboardButton("❌ تراجع وإلغاء", callback_data=f"cat_view_{cid}"))

        text = (
            f"⚠️ <b>هل أنت متأكد من حذف القسم «{c.get('name', cid)}»؟</b>\n"
            f"يحتوي هذا القسم على <b>{ch_cnt}</b> قناة.\n"
            f"اختر كيفية التعامل مع القنوات:"
        )
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=kb)
        bot.answer_callback_query(call.id)
        return

    if data.startswith("cat_del_confirm_"):
        parts = data.split("_")
        cid = parts[3]
        mode = parts[4]
        delete_ch = (mode == "both")
        db.delete_category(cid, delete_channels=delete_ch)
        bot.answer_callback_query(call.id, "تم حذف القسم بنجاح 🗑️", show_alert=True)
        call.data = "cat_p_1"
        handle_callbacks(call)
        return

    # 3. Channels Hub & Management Routing
    if data.startswith("ch_hub_"):
        text, kb = render_channels_page(category_id="all", page=1)
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=kb)
        bot.answer_callback_query(call.id)
        return

    if data.startswith("ch_cat_"):
        parts = data.split("_")
        cat_id = parts[2]
        page = int(parts[3])
        text, kb = render_channels_page(category_id=cat_id, page=page)
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=kb)
        bot.answer_callback_query(call.id)
        return

    if data.startswith("ch_add_in_"):
        cat_id = data[len("ch_add_in_"):]
        cat = db.get_category(cat_id)
        cat_name = cat.get("name", cat_id) if cat else "عام"
        user_states[user_id] = {
            "action": "wait_channel_input",
            "data": {"category_id": cat_id, "category_name": cat_name}
        }
        text = (
            f"➕ <b>إضافة قناة جديدة في قسم «{cat_name}»</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"أرسل الآن بيانات القناة بإحدى الطرق التالية:\n\n"
            f"🔹 <b>صيغة سريعة بسطر واحد:</b>\n"
            f"<code>اسم القناة | رابط البث | الجودة</code>\n"
            f"مثال:\n"
            f"<code>beIN Sports 1 | https://example.com/live.m3u8 | FHD</code>\n\n"
            f"🔹 <b>أو أرسل اسم القناة أولاً وسنطلب منك الرابط في الخطوة التالية.</b>"
        )
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=cancel_keyboard())
        bot.answer_callback_query(call.id)
        return

    if data.startswith("ch_view_"):
        chid = data[len("ch_view_"):]
        ch = db.get_channel(chid)
        if not ch:
            bot.answer_callback_query(call.id, "⚠️ القناة غير موجودة", show_alert=True)
            return

        cat_id = ch.get("category", "all")
        srv_count = len(ch.get("servers", []))
        dis_status = "🔴 معطلة في التطبيق" if ch.get("disabled", False) else "🟢 تعمل ونشطة"

        text = (
            f"📺 <b>تفاصيل القناة: {ch.get('name')}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🆔 المعرف: <code>{chid}</code>\n"
            f"📁 القسم: <b>{ch.get('categoryName', 'عام')}</b>\n"
            f"🔘 الحالة: <b>{dis_status}</b>\n"
            f"⚙️ الجودة: <b>{ch.get('quality', 'FHD')}</b>\n"
            f"🖥️ عدد السيرفرات/الجودات: <b>{srv_count}</b>\n"
            f"🔗 رابط البث الحالي:\n<code>{ch.get('url')}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━"
        )

        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.row(
            types.InlineKeyboardButton("✏️ تعديل الاسم", callback_data=f"ch_edname_{chid}"),
            types.InlineKeyboardButton("🔗 تعديل الرابط", callback_data=f"ch_edurl_{chid}")
        )
        kb.row(
            types.InlineKeyboardButton("⚙️ تعديل الجودة", callback_data=f"ch_edqual_{chid}"),
            types.InlineKeyboardButton("🎨 تعديل الشعار", callback_data=f"ch_edlogo_{chid}")
        )
        toggle_label = "🟢 تفعيل القناة" if ch.get("disabled", False) else "⏸️ تعطيل القناة"
        kb.row(
            types.InlineKeyboardButton(toggle_label, callback_data=f"ch_toggle_{chid}"),
            types.InlineKeyboardButton("🗑️ حذف القناة", callback_data=f"ch_del_{chid}")
        )
        kb.add(types.InlineKeyboardButton("🔙 رجوع لقنوات القسم", callback_data=f"ch_cat_{cat_id}_1"))

        bot.edit_message_text(text, chat_id, msg_id, reply_markup=kb)
        bot.answer_callback_query(call.id)
        return

    if data.startswith("ch_toggle_"):
        chid = data[len("ch_toggle_"):]
        db.toggle_channel_disabled(chid)
        bot.answer_callback_query(call.id, "تم تغيير حالة القناة بنجاح ✅")
        call.data = f"ch_view_{chid}"
        handle_callbacks(call)
        return

    if data.startswith("ch_del_"):
        chid = data[len("ch_del_"):]
        ch = db.get_channel(chid)
        cat_id = ch.get("category", "all") if ch else "all"
        db.delete_channel(chid)
        bot.answer_callback_query(call.id, "تم حذف القناة بنجاح 🗑️", show_alert=True)
        call.data = f"ch_cat_{cat_id}_1"
        handle_callbacks(call)
        return

    if data.startswith("ch_edname_"):
        chid = data[len("ch_edname_"):]
        user_states[user_id] = {"action": "wait_ch_new_name", "data": {"chid": chid}}
        bot.edit_message_text("✏️ <b>أرسل الآن الاسم الجديد للقناة:</b>", chat_id, msg_id, reply_markup=cancel_keyboard())
        bot.answer_callback_query(call.id)
        return

    if data.startswith("ch_edurl_"):
        chid = data[len("ch_edurl_"):]
        user_states[user_id] = {"action": "wait_ch_new_url", "data": {"chid": chid}}
        bot.edit_message_text("🔗 <b>أرسل الآن رابط البث المباشر الجديد للقناة:</b>", chat_id, msg_id, reply_markup=cancel_keyboard())
        bot.answer_callback_query(call.id)
        return

    if data.startswith("ch_edqual_"):
        chid = data[len("ch_edqual_"):]
        kb = types.InlineKeyboardMarkup(row_width=2)
        for q in ["4K", "FHD", "HD", "SD", "LOW"]:
            kb.add(types.InlineKeyboardButton(q, callback_data=f"ch_setqual_{chid}_{q}"))
        kb.add(types.InlineKeyboardButton("🔙 رجوع للقناة", callback_data=f"ch_view_{chid}"))
        bot.edit_message_text("⚙️ <b>اختر الجودة المطلوبة للقناة:</b>", chat_id, msg_id, reply_markup=kb)
        bot.answer_callback_query(call.id)
        return

    if data.startswith("ch_setqual_"):
        parts = data.split("_")
        chid = parts[2]
        qual = parts[3]
        db.update_channel_basic(chid, quality=qual)
        bot.answer_callback_query(call.id, f"تم ضبط الجودة إلى {qual} بنجاح ✅")
        call.data = f"ch_view_{chid}"
        handle_callbacks(call)
        return

    if data.startswith("ch_edlogo_"):
        chid = data[len("ch_edlogo_"):]
        user_states[user_id] = {"action": "wait_ch_new_logo", "data": {"chid": chid}}
        bot.edit_message_text(
            "🎨 <b>تعديل شعار/أيقونة القناة</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "أرسل الآن صورة الشعار مباشرة كصورة (Photo) في هذه المحادثة، أو رابط الصورة (URL)، أو إيموجي (مثل 📺 أو ⚽):",
            chat_id, msg_id, reply_markup=cancel_keyboard()
        )
        bot.answer_callback_query(call.id)
        return

    # 4. Updates Routing
    if data == "menu_update":
        text, kb = render_update_menu()
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=kb)
        bot.answer_callback_query(call.id)
        return

    if data == "up_upload_apk":
        user_states[user_id] = {"action": "wait_apk_file"}
        text = (
            "📤 <b>رفع ملف APK جديد مباشرة</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "أرسل الآن ملف الـ <b>APK</b> في هذه المحادثة كملف (Document).\n"
            "سيقوم السيرفر بحفظه وتوليد رابط تنزيل مباشر وفوري تلقائياً!"
        )
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=cancel_keyboard())
        bot.answer_callback_query(call.id)
        return

    if data == "up_set_url":
        user_states[user_id] = {"action": "wait_apk_url"}
        text = (
            "🔗 <b>إدخال رابط تحميل مباشر لـ APK</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "أرسل الآن رابط التحميل المباشر لملف التحديث (يبدأ بـ http:// أو https://):"
        )
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=cancel_keyboard())
        bot.answer_callback_query(call.id)
        return

    if data == "up_set_version":
        user_states[user_id] = {"action": "wait_apk_version"}
        text = (
            "🔢 <b>تعيين رقم واسم الإصدار الجديد</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "أرسل رقم الإصدار (Version Code) واسم الإصدار (Version Name) مفصولين بشرطة (|):\n"
            "مثال:\n"
            "<code>3 | 1.2</code>"
        )
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=cancel_keyboard())
        bot.answer_callback_query(call.id)
        return

    if data == "up_set_notes":
        user_states[user_id] = {"action": "wait_apk_notes"}
        bot.edit_message_text("📝 <b>أرسل الآن نص ملاحظات ومميزات التحديث الجديد:</b>", chat_id, msg_id, reply_markup=cancel_keyboard())
        bot.answer_callback_query(call.id)
        return

    if data == "up_toggle_force":
        up = db.get_app_update()
        new_force = not up.get("is_force", False)
        db.set_app_update(
            version_code=up.get("version_code", 2),
            version_name=up.get("version_name", "1.1"),
            download_url=up.get("download_url", ""),
            release_notes=up.get("release_notes", ""),
            is_force=new_force,
            enabled=up.get("enabled", True)
        )
        bot.answer_callback_query(call.id, f"تم تغيير نوع التحديث إلى {'إجباري 🔴' if new_force else 'اختياري 🟡'}", show_alert=True)
        call.data = "menu_update"
        handle_callbacks(call)
        return

    if data == "up_toggle_state":
        up = db.get_app_update()
        new_state = not up.get("enabled", False)
        db.toggle_app_update(new_state)
        bot.answer_callback_query(call.id, f"تم {'تفعيل ▶️' if new_state else 'تعطيل ⏸️'} التحديث للمستخدمين")
        call.data = "menu_update"
        handle_callbacks(call)
        return

    if data == "up_broadcast":
        up = db.get_app_update()
        title = "🚀 تحديث هام وجديد متوفر لتطبيق A2 TV!"
        msg = f"تم إطلاق الإصدار {up.get('version_name', 'الجديد')}! {up.get('release_notes', 'يرجى التحديث الآن.')}"
        db.add_notification(title, msg)
        bot.answer_callback_query(call.id, "تم إرسال إشعار التحديث لجميع المستخدمين بنجاح! 📢", show_alert=True)
        call.data = "menu_update"
        handle_callbacks(call)
        return

    # 5. Notifications Routing
    if data == "menu_notif":
        text, kb = render_notifications_menu()
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=kb)
        bot.answer_callback_query(call.id)
        return

    if data == "notif_new":
        user_states[user_id] = {"action": "wait_notif_title", "data": {}}
        prompt = (
            "🔔 <b>إرسال إشعار جديد لجميع المستخدمين</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "<b>الخطوة 1 من 3:</b> أرسل الآن <b>عنوان الإشعار</b> (مثال: 🔴 بث مباشر: قمة الليلة!):"
        )
        bot.edit_message_text(prompt, chat_id, msg_id, reply_markup=cancel_keyboard())
        bot.answer_callback_query(call.id)
        return

    if data == "notif_history":
        notifs = db.get_notifications(limit=10)
        if not notifs:
            bot.answer_callback_query(call.id, "لا توجد إشعارات مسجلة", show_alert=True)
            return
        kb = types.InlineKeyboardMarkup(row_width=1)
        for n in notifs:
            kb.add(types.InlineKeyboardButton(f"🗑️ حذف: {n.get('title')}", callback_data=f"notif_del_{n.get('id')}"))
        kb.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="menu_notif"))
        bot.edit_message_text("📋 <b>سجل آخر 10 إشعارات (اضغط على إشعار لحذفه):</b>", chat_id, msg_id, reply_markup=kb)
        bot.answer_callback_query(call.id)
        return

    if data.startswith("notif_del_"):
        nid = data[len("notif_del_"):]
        db.delete_notification(nid)
        bot.answer_callback_query(call.id, "تم حذف الإشعار بنجاح ✅")
        call.data = "notif_history"
        handle_callbacks(call)
        return

    # 6. Maintenance Routing
    if data == "menu_maint":
        text, kb = render_maintenance_menu()
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=kb)
        bot.answer_callback_query(call.id)
        return

    if data == "maint_enable":
        db.set_maintenance(True, admin_id=user_id)
        bot.answer_callback_query(call.id, "🔴 تم تشغيل وضع الصيانة وإيقاف التطبيق مؤقتاً!", show_alert=True)
        call.data = "menu_maint"
        handle_callbacks(call)
        return

    if data == "maint_disable":
        db.set_maintenance(False, admin_id=user_id)
        bot.answer_callback_query(call.id, "🟢 تم إيقاف وضع الصيانة وعاد التطبيق للعمل بنجاح!", show_alert=True)
        call.data = "menu_maint"
        handle_callbacks(call)
        return

    if data == "maint_set_msg":
        user_states[user_id] = {"action": "wait_maint_msg"}
        bot.edit_message_text("✏️ <b>أرسل الآن نص رسالة الصيانة التي ستظهر للمستخدمين:</b>", chat_id, msg_id, reply_markup=cancel_keyboard())
        bot.answer_callback_query(call.id)
        return

    if data == "maint_set_logo":
        user_states[user_id] = {"action": "wait_maint_logo"}
        text = (
            "🖼️ <b>تغيير شعار وصورة شاشة الصيانة</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "أرسل الآن رابط صورة الشعار، أو ارفع الصورة مباشرة في هذه المحادثة:"
        )
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=cancel_keyboard())
        bot.answer_callback_query(call.id)
        return

    if data == "maint_set_bg":
        user_states[user_id] = {"action": "wait_maint_bg"}
        text = (
            "🎨 <b>تغيير لون خلفية شاشة الصيانة</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "أرسل كود اللون بتنسيق Hex (مثال: <code>#0F0A18</code> أو <code>#1E1B4B</code> أو <code>#18181B</code>):"
        )
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=cancel_keyboard())
        bot.answer_callback_query(call.id)
        return

    # 7. Stats Routing
    if data == "menu_stats":
        text, kb = render_stats_menu()
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=kb)
        bot.answer_callback_query(call.id)
        return

# ----------------- Message Handler for Wizards -----------------

@bot.message_handler(content_types=['text', 'photo', 'document'])
def handle_text_messages(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        return

    state = user_states.get(user_id)
    if not state:
        return

    action = state.get("action")
    raw_text = message.text.strip() if message.text else ""

    # 1. Categories Wizard
    if action == "wait_cat_search":
        user_states.pop(user_id, None)
        text, kb = render_categories_page(page=1, search_query=raw_text)
        bot.reply_to(message, text, reply_markup=kb)
        return

    if action == "wait_cat_name":
        if len(raw_text) < 2:
            bot.reply_to(message, "⚠️ اسم القسم قصير جداً. يرجى إدخال اسم واضح للقسم:")
            return
        state["data"]["name"] = raw_text
        state["action"] = "wait_cat_icon"
        text = (
            f"📁 تم حفظ الاسم: <b>{raw_text}</b>\n\n"
            f"<b>الخطوة 2 من 2:</b> أرسل الآن <b>أيقونة أو شعار القسم</b>:\n"
            f"• يمكنك إرسال إيموجي (مثل: ⚽، 🎬، 🔴، 🕋)\n"
            f"• أو إرسال رابط صورة للشعار\n"
            f"• أو إرسال صورة مباشرة كملف أو صورة عادية!"
        )
        bot.reply_to(message, text, reply_markup=cancel_keyboard())
        return

    if action == "wait_cat_icon":
        cat_name = state["data"]["name"]
        icon = "📁"
        image_url = ""

        if message.photo:
            file_id = message.photo[-1].file_id
            file_info = bot.get_file(file_id)
            down = bot.download_file(file_info.file_path)
            fn = f"cat_{int(time.time())}.jpg"
            save_path = os.path.join(UPLOADS_DIR, fn)
            with open(save_path, "wb") as f:
                f.write(down)
            image_url = f"{PUBLIC_URL}/static/uploads/{fn}"
            icon = "🖼️"
        elif raw_text.startswith("http://") or raw_text.startswith("https://"):
            image_url = raw_text
            icon = "🖼️"
        elif raw_text:
            icon = raw_text.strip()[:4]

        # Generate unique safe ID
        clean_id = re.sub(r'[^a-zA-Z0-9]+', '_', cat_name).strip('_').lower()
        if not clean_id or len(clean_id) < 2:
            import hashlib
            clean_id = f"cat_{hashlib.md5(cat_name.encode('utf-8')).hexdigest()[:6]}"
        cat_id = clean_id

        res = db.add_category(cat_id, cat_name, icon=icon, image=image_url)
        user_states.pop(user_id, None)

        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.add(types.InlineKeyboardButton(f"➕ إضافة قنوات داخل «{cat_name}»", callback_data=f"ch_add_in_{cat_id}"))
        kb.add(types.InlineKeyboardButton("🗂️ عرض قائمة الأقسام", callback_data="cat_p_1"))
        kb.add(types.InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu"))

        success_text = (
            f"🎉 <b>تم إنشاء القسم بنجاح!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📁 اسم القسم: <b>{icon} {cat_name}</b>\n"
            f"🆔 المعرف البرمجي: <code>{cat_id}</code>\n"
            f"🖼️ الشعار: <b>{'موجود ✅' if image_url else 'إيموجي فقط'}</b>\n\n"
            f"يظهر القسم فوراً داخل تطبيق A2 TV ويتم حفظه بشكل دائم!"
        )
        bot.reply_to(message, success_text, reply_markup=kb)
        return

    if action == "wait_cat_new_name":
        cid = state["data"]["cid"]
        db.update_category(cid, new_name=raw_text)
        user_states.pop(user_id, None)
        bot.reply_to(message, f"✅ تم تعديل اسم القسم إلى: <b>{raw_text}</b> بنجاح!", reply_markup=back_keyboard(f"cat_view_{cid}"))
        return

    if action == "wait_cat_new_icon":
        cid = state["data"]["cid"]
        icon = "📁"
        image_url = ""
        if message.photo:
            file_id = message.photo[-1].file_id
            file_info = bot.get_file(file_id)
            down = bot.download_file(file_info.file_path)
            fn = f"cat_{int(time.time())}.jpg"
            save_path = os.path.join(UPLOADS_DIR, fn)
            with open(save_path, "wb") as f:
                f.write(down)
            image_url = f"{PUBLIC_URL}/static/uploads/{fn}"
            icon = "🖼️"
        elif raw_text.startswith("http://") or raw_text.startswith("https://"):
            image_url = raw_text
            icon = "🖼️"
        elif raw_text:
            icon = raw_text.strip()[:4]

        db.update_category(cid, new_icon=icon, new_image=image_url)
        user_states.pop(user_id, None)
        bot.reply_to(message, "✅ تم تحديث أيقونة وشعار القسم بنجاح!", reply_markup=back_keyboard(f"cat_view_{cid}"))
        return

    # 2. Channels Wizard
    if action == "wait_channel_input":
        d = state["data"]
        cat_id = d["category_id"]
        cat_name = d["category_name"]

        # Check piped format: Name | URL | Quality
        if "|" in raw_text:
            parts = [p.strip() for p in raw_text.split("|")]
            ch_name = parts[0]
            ch_url = parts[1]
            ch_qual = parts[2] if len(parts) > 2 else "FHD"

            ch = db.add_single_channel(name=ch_name, url=ch_url, category_id=cat_id, category_name=cat_name, quality=ch_qual)
            user_states.pop(user_id, None)

            kb = types.InlineKeyboardMarkup(row_width=1)
            kb.add(types.InlineKeyboardButton(f"➕ إضافة قناة أخرى في «{cat_name}»", callback_data=f"ch_add_in_{cat_id}"))
            kb.add(types.InlineKeyboardButton("📺 قنوات هذا القسم", callback_data=f"ch_cat_{cat_id}_1"))
            kb.add(types.InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu"))

            text = (
                f"🎉 <b>تمت إضافة القناة بنجاح!</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📺 القناة: <b>{ch['name']}</b>\n"
                f"📁 القسم: <b>{cat_name}</b>\n"
                f"⚙️ الجودة: <b>{ch.get('quality', 'FHD')}</b>\n"
                f"🔗 الرابط:\n<code>{ch['url']}</code>\n\n"
                f"ستظهر القناة فوراً داخل تطبيق A2 TV في القسم الصحيح!"
            )
            bot.reply_to(message, text, reply_markup=kb)
            return
        elif raw_text.startswith("http://") or raw_text.startswith("https://"):
            if "name" in d:
                ch_name = d["name"]
                ch = db.add_single_channel(name=ch_name, url=raw_text, category_id=cat_id, category_name=cat_name, quality="FHD")
                user_states.pop(user_id, None)
                kb = types.InlineKeyboardMarkup(row_width=1)
                kb.add(types.InlineKeyboardButton(f"➕ إضافة قناة أخرى في «{cat_name}»", callback_data=f"ch_add_in_{cat_id}"))
                kb.add(types.InlineKeyboardButton("📺 قنوات هذا القسم", callback_data=f"ch_cat_{cat_id}_1"))
                kb.add(types.InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu"))
                bot.reply_to(message, f"🎉 <b>تمت إضافة قناة «{ch_name}» بنجاح!</b>", reply_markup=kb)
                return
            else:
                bot.reply_to(message, "⚠️ يرجى إرسال اسم القناة أولاً:")
                return
        else:
            # User sent only the channel name
            state["data"]["name"] = raw_text
            bot.reply_to(message, f"📺 اسم القناة: <b>{raw_text}</b>\n\nأرسل الآن <b>رابط البث المباشر</b> للقناة:")
            return

    if action == "wait_ch_new_name":
        chid = state["data"]["chid"]
        db.update_channel_basic(chid, name=raw_text)
        user_states.pop(user_id, None)
        bot.reply_to(message, "✅ تم تعديل اسم القناة بنجاح!", reply_markup=back_keyboard(f"ch_view_{chid}"))
        return

    if action == "wait_ch_new_url":
        chid = state["data"]["chid"]
        db.update_channel_basic(chid, url=raw_text)
        user_states.pop(user_id, None)
        bot.reply_to(message, "✅ تم تعديل رابط بث القناة بنجاح!", reply_markup=back_keyboard(f"ch_view_{chid}"))
        return

    if action == "wait_ch_new_logo":
        chid = state["data"]["chid"]
        logo_val = ""
        if message.photo:
            file_id = message.photo[-1].file_id
            file_info = bot.get_file(file_id)
            down = bot.download_file(file_info.file_path)
            fn = f"ch_{chid}_{int(time.time())}.jpg"
            save_path = os.path.join(UPLOADS_DIR, fn)
            with open(save_path, "wb") as f:
                f.write(down)
            logo_val = f"{PUBLIC_URL}/static/uploads/{fn}"
        elif raw_text.startswith("http://") or raw_text.startswith("https://"):
            logo_val = raw_text
        elif raw_text:
            logo_val = raw_text.strip()[:6]

        db.update_channel_basic(chid, logo=logo_val)
        user_states.pop(user_id, None)
        bot.reply_to(message, "✅ تم تحديث شعار وأيقونة القناة بنجاح!", reply_markup=back_keyboard(f"ch_view_{chid}"))
        return

    # 3. APK Update Wizard
    if action == "wait_apk_file":
        if not message.document:
            bot.reply_to(message, "⚠️ يرجى إرسال ملف APK صالح (Document):")
            return
        doc = message.document
        if not doc.file_name.lower().endswith(".apk"):
            bot.reply_to(message, "⚠️ الملف المرسل ليس ملف APK. تأكد من إرسال ملف ينتهي بـ .apk:")
            return

        bot.reply_to(message, "⏳ جاري تحميل وحفظ ملف الـ APK على السيرفر...")
        file_info = bot.get_file(doc.file_id)
        down = bot.download_file(file_info.file_path)

        apk_filename = f"A2TV_v{int(time.time())}.apk"
        save_path = os.path.join(UPDATES_DIR, apk_filename)
        with open(save_path, "wb") as f:
            f.write(down)

        apk_direct_url = f"{PUBLIC_URL}/static/{apk_filename}"
        up = db.get_app_update()
        new_v_code = up.get("version_code", 1) + 1
        new_v_name = f"1.{new_v_code}"

        db.set_app_update(
            version_code=new_v_code,
            version_name=new_v_name,
            download_url=apk_direct_url,
            release_notes="تحسينات عامة وسرعة إضافية في تشغيل القنوات",
            is_force=True,
            enabled=True
        )
        user_states.pop(user_id, None)

        success_text = (
            "🎉 <b>تم رفع ملف الـ APK وتحديث السيرفر بنجاح!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📦 اسم الملف: <code>{apk_filename}</code>\n"
            f"🔢 رقم الإصدار: <b>{new_v_code}</b>\n"
            f"🏷️ اسم الإصدار: <b>{new_v_name}</b>\n"
            f"⚠️ نوع التحديث: <b>إجباري 🔴</b>\n"
            f"🔗 رابط التحميل المباشر:\n<code>{apk_direct_url}</code>\n\n"
            "ستظهر نافذة التحديث الإجباري لجميع المستخدمين عند فتح التطبيق!"
        )
        bot.reply_to(message, success_text, reply_markup=back_keyboard("menu_update"))
        return

    if action == "wait_apk_url":
        if not raw_text.startswith("http://") and not raw_text.startswith("https://"):
            bot.reply_to(message, "⚠️ الرابط غير صالح. يرجى إرسال رابط يبدأ بـ http:// أو https://")
            return
        up = db.get_app_update()
        new_v_code = up.get("version_code", 1) + 1
        db.set_app_update(
            version_code=new_v_code,
            version_name=up.get("version_name", "1.1"),
            download_url=raw_text,
            release_notes=up.get("release_notes", "تحديث جديد لتطبيق A2 TV"),
            is_force=up.get("is_force", True),
            enabled=True
        )
        user_states.pop(user_id, None)
        bot.reply_to(message, f"✅ تم تعيين رابط التحميل المباشر بنجاح ورقم الإصدار إلى {new_v_code}!", reply_markup=back_keyboard("menu_update"))
        return

    if action == "wait_apk_version":
        parts = [p.strip() for p in raw_text.split("|")]
        try:
            v_code = int(parts[0])
            v_name = parts[1] if len(parts) > 1 else f"1.{v_code}"
            up = db.get_app_update()
            db.set_app_update(
                version_code=v_code,
                version_name=v_name,
                download_url=up.get("download_url", ""),
                release_notes=up.get("release_notes", "تحديث جديد"),
                is_force=up.get("is_force", True),
                enabled=True
            )
            user_states.pop(user_id, None)
            bot.reply_to(message, f"✅ تم تحديث رقم الإصدار إلى: <b>{v_code}</b> ({v_name}) بنجاح!", reply_markup=back_keyboard("menu_update"))
        except Exception:
            bot.reply_to(message, "⚠️ صيغة غير صحيحة. يرجى إرسال: <code>رقم_الإصدار | اسم_الإصدار</code> مثل <code>3 | 1.2</code>")
        return

    if action == "wait_apk_notes":
        up = db.get_app_update()
        db.set_app_update(
            version_code=up.get("version_code", 2),
            version_name=up.get("version_name", "1.1"),
            download_url=up.get("download_url", ""),
            release_notes=raw_text,
            is_force=up.get("is_force", True),
            enabled=True
        )
        user_states.pop(user_id, None)
        bot.reply_to(message, "✅ تم حفظ ملاحظات التحديث بنجاح!", reply_markup=back_keyboard("menu_update"))
        return

    # 4. Notifications Wizard
    if action == "wait_notif_title":
        state["data"]["title"] = raw_text
        state["action"] = "wait_notif_msg"
        bot.reply_to(message, f"📌 العنوان: <b>{raw_text}</b>\n\n<b>الخطوة 2 من 3:</b> أرسل الآن <b>نص رسالة الإشعار</b>:")
        return

    if action == "wait_notif_msg":
        state["data"]["msg"] = raw_text
        state["action"] = "wait_notif_image"
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("⏭️ تخطي بدون صورة وإرسال فوراً", callback_data="notif_skip_image"))
        bot.reply_to(message, "🖼️ <b>الخطوة 3 من 3:</b> هل تريد إرفاق شعار أو صورة للإشعار؟\nأرسل صورة مباشرة أو رابط صورة، أو اضغط زر «تخطي»:", reply_markup=kb)
        return

    if action == "wait_notif_image":
        title = state["data"]["title"]
        msg_content = state["data"]["msg"]
        image_url = ""

        if message.photo:
            file_id = message.photo[-1].file_id
            file_info = bot.get_file(file_id)
            down = bot.download_file(file_info.file_path)
            fn = f"notif_{int(time.time())}.jpg"
            save_path = os.path.join(UPLOADS_DIR, fn)
            with open(save_path, "wb") as f:
                f.write(down)
            image_url = f"{PUBLIC_URL}/static/uploads/{fn}"
        elif raw_text.startswith("http://") or raw_text.startswith("https://"):
            image_url = raw_text

        db.add_notification(title, msg_content, image=image_url)
        user_states.pop(user_id, None)

        bot.reply_to(
            message,
            f"🎉 <b>تم إرسال الإشعار لجميع المستخدمين بنجاح!</b> 📢\n\n<b>{title}</b>\n{msg_content}\n"
            f"🖼️ الصورة: {'مرفقة ✅' if image_url else 'بدون صورة'}",
            reply_markup=back_keyboard("menu_notif")
        )
        return

    # 5. Maintenance Wizard
    if action == "wait_maint_msg":
        db.set_maintenance(True, message=raw_text, admin_id=user_id)
        user_states.pop(user_id, None)
        bot.reply_to(message, "✅ تم حفظ رسالة الصيانة بنجاح!", reply_markup=back_keyboard("menu_maint"))
        return

    if action == "wait_maint_logo":
        logo_url = ""
        if message.photo:
            file_id = message.photo[-1].file_id
            file_info = bot.get_file(file_id)
            down = bot.download_file(file_info.file_path)
            fn = f"maint_{int(time.time())}.jpg"
            save_path = os.path.join(UPLOADS_DIR, fn)
            with open(save_path, "wb") as f:
                f.write(down)
            logo_url = f"{PUBLIC_URL}/static/uploads/{fn}"
        elif raw_text.startswith("http://") or raw_text.startswith("https://"):
            logo_url = raw_text

        m = db.get_maintenance()
        db.set_maintenance(m.get("enabled", False), image=logo_url, admin_id=user_id)
        user_states.pop(user_id, None)
        bot.reply_to(message, "✅ تم تحديث شعار وصورة شاشة الصيانة بنجاح!", reply_markup=back_keyboard("menu_maint"))
        return

    if action == "wait_maint_bg":
        m = db.get_maintenance()
        db.set_maintenance(m.get("enabled", False), bg_color=raw_text, admin_id=user_id)
        user_states.pop(user_id, None)
        bot.reply_to(message, f"✅ تم تحديث لون خلفية الصيانة إلى: <code>{raw_text}</code> بنجاح!", reply_markup=back_keyboard("menu_maint"))
        return

@bot.callback_query_handler(func=lambda call: call.data == "notif_skip_image")
def handle_skip_notif_image(call):
    user_id = call.from_user.id
    state = user_states.get(user_id)
    if state and state.get("action") == "wait_notif_image":
        title = state["data"]["title"]
        msg_content = state["data"]["msg"]
        db.add_notification(title, msg_content, image="")
        user_states.pop(user_id, None)
        bot.edit_message_text(
            f"🎉 <b>تم إرسال الإشعار لجميع المستخدمين بنجاح!</b> 📢\n\n<b>{title}</b>\n{msg_content}",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=back_keyboard("menu_notif")
        )
        bot.answer_callback_query(call.id)
    else:
        bot.answer_callback_query(call.id)

def start_bot_polling():
    if not BOT_INITIALIZED:
        logger.warning("Bot token not configured properly, polling skipped.")
        return
    logger.info("Starting Telegram Bot Polling with clean modern UI...")
    bot.infinity_polling(timeout=20, long_polling_timeout=20)

run_bot = start_bot_polling

if __name__ == "__main__":
    start_bot_polling()
