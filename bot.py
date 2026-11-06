import csv
import html
import io
import logging
import os
import re
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from telegram import (InlineKeyboardButton, InlineKeyboardMarkup, InputFile, KeyboardButton,
                      ReplyKeyboardMarkup, ReplyKeyboardRemove, Update)
from telegram.error import BadRequest
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          ContextTypes, ConversationHandler, MessageHandler, filters)

HERE = Path(__file__).resolve().parent
DB_FILE = HERE / "leads.db"
LEGACY_CSV = HERE / "leads.csv"  # eski "baza": birinchi ishga tushishda DB ga ko'chiriladi
LEAD_FIELDS = ["vaqt", "ism", "kompaniya", "telefon", "yonalish", "username", "chat_id"]

# O'zbekistonda yozgi vaqt yo'q, shuning uchun tzdata paketisiz qat'iy UTC+5 yetarli.
TASHKENT = timezone(timedelta(hours=5))

NAME, COMPANY, PHONE, TOPIC = range(4)

TOPICS = {
    "hisobot": "Moliyaviy hisobot",
    "crm": "CRM",
    "erp": "ERP",
    "boshqa": "Boshqa",
}

WELCOME = (
    "Salom! Bu UstunSys.\n\n"
    "Moliyaviy hisobot, CRM va ERP veb-dasturlarini yasaymiz, SAP va Bitrix24 bilan ishlaymiz.\n"
    "Maqsad: Excelga qaramlikni kamaytirish.\n\n"
    "Quyidan tanlang:"
)

SERVICES = (
    "Xizmatlarimiz:\n"
    "- Moliyaviy hisobot dashboardi: debitor, pul oqimi, marja\n"
    "- CRM: mijozlar, bitimlar, savdo jarayoni\n"
    "- ERP integratsiya: ombor, buxgalteriya, sotuv\n"
    "- SAP va Bitrix24 dan ma'lumot olish\n\n"
    "Qanday ishlaymiz: tahlil, demo, ishga tushirish, qo'llab-quvvatlash."
)

PRICE = (
    "Narx hajmga bog'liq: nechta hisobot kerak va qaysi tizimdan ma'lumot olinadi.\n"
    "Aniq narx va muddatni 15 daqiqalik suhbatdan keyin aytamiz. "
    "Bepul demo uchun so'rov qoldiring."
)

CONTACT = "Savolingiz bo'lsa, shu botga yozing yoki Instagramda @ustunsys ga DM yuboring."

MENU_TEXTS = {"services": SERVICES, "price": PRICE, "contact": CONTACT}


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Bepul demo / mini-audit", callback_data="lead")],
        [InlineKeyboardButton("Xizmatlar", callback_data="services"),
         InlineKeyboardButton("Narx", callback_data="price")],
        [InlineKeyboardButton("Aloqa", callback_data="contact")],
    ])


def topic_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(v, callback_data=f"t_{k}")]
                                 for k, v in TOPICS.items()])


def normalize_phone(text: str) -> str | None:
    """+998901234567 ko'rinishiga keltiradi; yaroqsiz bo'lsa None."""
    digits = re.sub(r"\D", "", text)
    if len(digits) == 10 and digits.startswith("8"):  # eski format: 8 90 123 45 67
        digits = digits[1:]
    if len(digits) == 9:
        digits = "998" + digits
    if len(digits) == 12 and digits.startswith("998"):
        return "+" + digits
    return None


def clean_text(text: str, limit: int) -> str:
    """Bo'shliqlarni bittaga qisqartiradi (qator ko'chishlari ham), uzunlikni cheklaydi."""
    return " ".join(text.split())[:limit]


# ---------------------------------------------------------------- baza (SQLite)

SCHEMA_VERSION = 2


def db_connect(path: Path | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or DB_FILE, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(path: Path | None = None, legacy_csv: Path | None = None) -> None:
    """Jadvalni yaratadi va (faqat bir marta) eski leads.csv ni import qiladi.

    Sxema versiyasi PRAGMA user_version da saqlanadi: keyingi o'zgarishlar shu yerga
    `if version < 2: ...` ko'rinishida qo'shiladi.
    """
    legacy_csv = legacy_csv if legacy_csv is not None else LEGACY_CSV
    with closing(db_connect(path)) as conn, conn:
        conn.execute("PRAGMA journal_mode=WAL")
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version < 1:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS leads (
                    id         INTEGER PRIMARY KEY,
                    created_at TEXT    NOT NULL,      -- 'YYYY-MM-DD HH:MM', Toshkent vaqti
                    name       TEXT    NOT NULL,
                    company    TEXT    NOT NULL,
                    phone      TEXT    NOT NULL,
                    topic      TEXT    NOT NULL,
                    username   TEXT    NOT NULL DEFAULT '',
                    chat_id    INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_leads_created ON leads(created_at);
                CREATE INDEX IF NOT EXISTS idx_leads_chat    ON leads(chat_id);
            """)
            imported = _import_legacy_csv(conn, legacy_csv)
            if imported:
                logging.info("leads.csv dan %s ta so'rov bazaga ko'chirildi", imported)
        if version < 2:
            conn.execute("CREATE TABLE IF NOT EXISTS settings ("
                         " key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        if version < SCHEMA_VERSION:
            conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")


def get_setting(key: str, default: str, path: Path | None = None) -> str:
    with closing(db_connect(path)) as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default


def set_setting(key: str, value: str, path: Path | None = None) -> None:
    with closing(db_connect(path)) as conn, conn:
        conn.execute("INSERT INTO settings (key, value) VALUES (?, ?)"
                     " ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))


def skip_phone_enabled() -> bool:
    """'Raqamsiz davom etish' tugmasi ko'rinadimi. Standart holatda yoqilgan."""
    return get_setting("skip_phone", "1") == "1"


def _import_legacy_csv(conn: sqlite3.Connection, path: Path) -> int:
    if not path.exists():
        return 0
    with path.open(newline="", encoding="utf-8-sig") as f:
        rows = [
            (r.get("vaqt", ""), r.get("ism", ""), r.get("kompaniya", ""), r.get("telefon", ""),
             r.get("yonalish", ""), r.get("username", ""), int(r.get("chat_id") or 0))
            for r in csv.DictReader(f)
        ]
    conn.executemany(
        "INSERT INTO leads (created_at, name, company, phone, topic, username, chat_id)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
    return len(rows)


def save_lead(lead: dict, path: Path | None = None) -> int:
    with closing(db_connect(path)) as conn, conn:
        cur = conn.execute(
            "INSERT INTO leads (created_at, name, company, phone, topic, username, chat_id)"
            " VALUES (:vaqt, :ism, :kompaniya, :telefon, :yonalish, :username, :chat_id)", lead)
        return cur.lastrowid


def fetch_leads(path: Path | None = None) -> list[sqlite3.Row]:
    with closing(db_connect(path)) as conn:
        return conn.execute(
            "SELECT created_at, name, company, phone, topic, username, chat_id"
            " FROM leads ORDER BY id").fetchall()


def lead_stats(path: Path | None = None) -> dict:
    today = datetime.now(TASHKENT).strftime("%Y-%m-%d")
    week_ago = (datetime.now(TASHKENT) - timedelta(days=7)).strftime("%Y-%m-%d")
    with closing(db_connect(path)) as conn:
        total, today_n, week_n, unique = conn.execute(
            "SELECT COUNT(*), SUM(created_at >= ?), SUM(created_at >= ?), COUNT(DISTINCT chat_id)"
            " FROM leads", (today, week_ago)).fetchone()
        by_topic = conn.execute(
            "SELECT topic, COUNT(*) FROM leads GROUP BY topic ORDER BY 2 DESC").fetchall()
    return {"total": total, "today": today_n or 0, "week": week_n or 0, "unique": unique,
            "by_topic": [(t, n) for t, n in by_topic]}


def _excel_safe(value) -> str:
    """CSV/formula injection'dan himoya: Excel '=', '+', '-', '@' bilan boshlangan matnni formula
    deb bajaradi. Telefon raqami o'zimiz normallashtirgan qiymat, unga tegmaymiz."""
    s = "" if value is None else str(value)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def leads_csv_bytes(rows: list[sqlite3.Row]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(LEAD_FIELDS)
    for r in rows:
        w.writerow([r["created_at"], _excel_safe(r["name"]), _excel_safe(r["company"]),
                    r["phone"], r["topic"], r["username"], r["chat_id"]])
    return buf.getvalue().encode("utf-8-sig")  # BOM: Excel kirillcha/o'zbekchani to'g'ri ochadi


def admin_ids() -> set[int]:
    raw = os.getenv("ADMIN_CHAT_ID", "")
    return {int(x) for x in re.split(r"[,\s]+", raw) if x.lstrip("-").isdigit()}


# ---------------------------------------------------------------- handlerlar

async def safe_answer(q, text: str | None = None, **kwargs) -> None:
    """Tugma bosilganini tasdiqlash. Bot o'chiq turganda bosilgan tugma uchun Telegram
    'Query is too old' qaytaradi: bu handlerni to'xtatmasligi kerak, javob baribir yuboriladi."""
    try:
        await q.answer(text, **kwargs)
    except BadRequest as e:
        logging.info("Callback tasdiqlanmadi (%s)", e)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(WELCOME, reply_markup=main_menu())


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Sizning chat ID: {update.effective_chat.id}")


async def menu_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await safe_answer(q)
    await q.message.reply_text(MENU_TEXTS[q.data], reply_markup=main_menu())


async def stale_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Eski/muddati o'tgan tugma (masalan bot qayta ishga tushgandan keyin): soat belgisi
    osilib qolmasin va foydalanuvchi nima qilishni bilsin."""
    q = update.callback_query
    await safe_answer(q, "Bu tugma eskirgan. Qaytadan boshlang.")
    await q.message.reply_text(WELCOME, reply_markup=main_menu())


async def lead_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await safe_answer(q)
    context.user_data.clear()
    await q.message.reply_text("Ismingiz nima?\n(Bekor qilish: /cancel)",
                               reply_markup=ReplyKeyboardRemove())
    return NAME


async def got_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = clean_text(update.message.text, 80)
    if len(name) < 2:
        await update.message.reply_text("Ismingizni yozing (kamida 2 harf).")
        return NAME
    context.user_data["ism"] = name
    await update.message.reply_text("Kompaniyangiz nomi?")
    return COMPANY


async def got_company(update: Update, context: ContextTypes.DEFAULT_TYPE):
    company = clean_text(update.message.text, 120)
    if not company:
        await update.message.reply_text("Kompaniya nomini yozing.")
        return COMPANY
    context.user_data["kompaniya"] = company
    await update.message.reply_text(phone_prompt(), reply_markup=phone_keyboard())
    return PHONE


SEND_PHONE = "📱 Raqamimni yuborish"
SKIP_PHONE = "Raqamsiz davom etish"


def phone_prompt() -> str:
    text = "Telefon raqamingizni yuborish uchun pastdagi \"Raqamimni yuborish\" tugmasini bosing."
    if skip_phone_enabled():
        text += "\nRaqam bermasangiz, \"Raqamsiz davom etish\" ni bosing: Telegram orqali yozamiz."
    return text


def phone_keyboard() -> ReplyKeyboardMarkup:
    rows = [[KeyboardButton(SEND_PHONE, request_contact=True)]]
    if skip_phone_enabled():
        rows.append([KeyboardButton(SKIP_PHONE)])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, one_time_keyboard=True)


def contact_phone(raw: str) -> str:
    """Telegram tasdiqlagan raqam: O'zbekiston raqami +998XXXXXXXXX ko'rinishiga keltiriladi,
    chet el raqami ham qabul qilinadi (mijoz yo'qolmasin), faqat '+' qo'shiladi."""
    return normalize_phone(raw) or "+" + re.sub(r"\D", "", raw)


async def got_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    contact = msg.contact
    # Faqat o'z raqami: "Raqamimni yuborish" tugmasi user_id ni foydalanuvchining o'zi qilib yuboradi.
    # Qo'lda yozilgan matn yoki boshqa odamning kontaktini ulashish qabul qilinmaydi.
    if contact and contact.user_id == update.effective_user.id:
        context.user_data["telefon"] = contact_phone(contact.phone_number)
    elif msg.text == SKIP_PHONE and skip_phone_enabled():
        context.user_data["telefon"] = ""  # adminga Telegram profil havolasi yuboriladi
    else:
        await msg.reply_text(
            "Iltimos, raqamni qo'lda yozmang: pastdagi tugmalardan birini bosing.",
            reply_markup=phone_keyboard())
        return PHONE
    await update.message.reply_text("Rahmat.", reply_markup=ReplyKeyboardRemove())
    await update.message.reply_text("Nima kerak?", reply_markup=topic_menu())
    return TOPIC


async def topic_hint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Quyidagi tugmalardan birini tanlang:", reply_markup=topic_menu())
    return TOPIC


async def got_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await safe_answer(q)
    user = update.effective_user
    lead = {
        "vaqt": datetime.now(TASHKENT).strftime("%Y-%m-%d %H:%M"),
        "ism": context.user_data.get("ism", ""),
        "kompaniya": context.user_data.get("kompaniya", ""),
        "telefon": context.user_data.get("telefon", ""),
        "yonalish": TOPICS.get(q.data.removeprefix("t_"), "Boshqa"),
        "username": f"@{user.username}" if user.username else "",
        "chat_id": update.effective_chat.id,
    }
    context.user_data.clear()
    try:
        save_lead(lead)
    except sqlite3.Error:
        # Baza ishlamasa ham so'rov yo'qolmasin: adminga baribir yuboriladi.
        logging.exception("So'rovni bazaga yozib bo'lmadi")
    shown = lead | {"telefon": lead["telefon"] or "yo'q — Telegram orqali yozing"}
    note = ("Yangi so'rov:\n"
            + "\n".join(f"{k}: {html.escape(str(v))}" for k, v in shown.items() if v != "")
            + f"\nprofil: {user.mention_html()}")  # username bo'lmasa ham bosib yozish mumkin
    for cid in admin_ids():
        try:
            await context.bot.send_message(cid, note, parse_mode="HTML")
        except Exception:
            logging.exception("Admin %s ga yuborib bo'lmadi", cid)
    await q.message.reply_text(
        "So'rovingiz qabul qilindi. Tez orada siz bilan bog'lanamiz.",
        reply_markup=main_menu())
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Bekor qilindi.", reply_markup=ReplyKeyboardRemove())
    await update.message.reply_text(WELCOME, reply_markup=main_menu())
    return ConversationHandler.END


async def timeout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    if update and update.effective_chat:
        await context.bot.send_message(
            update.effective_chat.id,
            "Vaqt tugadi, so'rov to'xtatildi. Qaytadan boshlash uchun /start bosing.",
            reply_markup=ReplyKeyboardRemove())


async def export_leads(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = fetch_leads()
    if not rows:
        await update.message.reply_text("Hozircha so'rov yo'q.")
        return
    name = f"leads_{datetime.now(TASHKENT):%Y-%m-%d}.csv"
    await update.message.reply_document(InputFile(leads_csv_bytes(rows), filename=name),
                                        caption=f"Jami: {len(rows)} ta so'rov")


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = lead_stats()
    lines = [f"Jami: {s['total']} (bugun {s['today']}, 7 kunda {s['week']})",
             f"Turli mijozlar: {s['unique']}"]
    lines += [f"- {t}: {n}" for t, n in s["by_topic"]]
    await update.message.reply_text("\n".join(lines))


def settings_menu() -> InlineKeyboardMarkup:
    state = "yoqilgan ✅" if skip_phone_enabled() else "o'chirilgan ❌"
    return InlineKeyboardMarkup([[InlineKeyboardButton(
        f"Raqamsiz davom etish: {state}", callback_data="cfg_skip_phone")]])


async def settings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Sozlamalar (o'zgartirish uchun bosing):",
                                    reply_markup=settings_menu())


async def toggle_skip_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id not in admin_ids():
        await safe_answer(q, "Bu faqat admin uchun.", show_alert=True)
        return
    set_setting("skip_phone", "0" if skip_phone_enabled() else "1")
    await safe_answer(q, "Saqlandi")
    await q.edit_message_reply_markup(reply_markup=settings_menu())


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    logging.error("Handler xatosi", exc_info=context.error)


def build_app(token: str) -> Application:
    app = Application.builder().token(token).build()
    # UpdateType.MESSAGE: tahrirlangan xabarlar (edited_message) handlerga tushmasin,
    # aks holda update.message None bo'lib xato chiqadi.
    new_msg = filters.UpdateType.MESSAGE & ~filters.COMMAND
    text = new_msg & filters.TEXT
    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(lead_start, pattern="^lead$")],
        states={
            NAME: [MessageHandler(text, got_name)],
            COMPANY: [MessageHandler(text, got_company)],
            PHONE: [MessageHandler(new_msg, got_phone)],  # kontakt bo'lmasa got_phone tugmani so'raydi
            TOPIC: [CallbackQueryHandler(got_topic, pattern="^t_"),
                    MessageHandler(text, topic_hint)],
            ConversationHandler.TIMEOUT: [MessageHandler(filters.ALL, timeout),
                                          CallbackQueryHandler(timeout)],
        },
        fallbacks=[CommandHandler("cancel", cancel), CommandHandler("start", cancel)],
        allow_reentry=True,  # suhbat o'rtasida "Bepul demo" qayta bosilsa, boshidan boshlanadi
        conversation_timeout=1800,
    )
    # Tartib muhim: bitta guruhda birinchi mos handler ishlaydi. Suhbat birinchi turishi kerak,
    # aks holda suhbat o'rtasidagi /start uni yopmaydi va keyingi matn "ism" bo'lib ketadi.
    app.add_handler(conv)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("myid", myid))
    admins = filters.Chat(chat_id=admin_ids())
    app.add_handler(CommandHandler("export", export_leads, filters=admins))
    app.add_handler(CommandHandler("stats", stats, filters=admins))
    app.add_handler(CommandHandler("sozlamalar", settings_cmd, filters=admins))
    app.add_handler(CallbackQueryHandler(toggle_skip_phone, pattern="^cfg_skip_phone$"))
    app.add_handler(CallbackQueryHandler(menu_click, pattern="^(services|price|contact)$"))
    app.add_handler(CallbackQueryHandler(stale_button))
    app.add_error_handler(on_error)
    return app


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    load_dotenv(HERE / ".env")
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        sys.exit("BOT_TOKEN topilmadi. .env fayliga BOT_TOKEN=... yozing (README ga qarang).")
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # INFO loglarda token URL ichida chiqadi
    init_db()
    if not admin_ids():
        logging.warning("ADMIN_CHAT_ID bo'sh: so'rovlar faqat bazaga yoziladi, xabar kelmaydi")
    print("Bot ishga tushdi. To'xtatish: Ctrl+C")
    build_app(token).run_polling()


if __name__ == "__main__":
    main()
