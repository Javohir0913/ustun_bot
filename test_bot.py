import asyncio
import csv
import io
import json

import pytest
from telegram import Update
from telegram.ext import Application
from telegram.request import BaseRequest

import bot


@pytest.mark.parametrize("raw,expected", [
    ("+998 90 123 45 67", "+998901234567"),
    ("998901234567", "+998901234567"),
    ("90 123 45 67", "+998901234567"),
    ("(90) 123-45-67", "+998901234567"),
    ("8 90 123 45 67", "+998901234567"),
    ("12345", None),
    ("abc", None),
    ("+7 999 123 45 67", None),
])
def test_normalize_phone(raw, expected):
    assert bot.normalize_phone(raw) == expected


def test_clean_text():
    assert bot.clean_text("  Ali \n  Valiyev ", 80) == "Ali Valiyev"
    assert bot.clean_text("x" * 100, 10) == "x" * 10


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "leads.db"
    monkeypatch.setattr(bot, "DB_FILE", path)
    monkeypatch.setattr(bot, "LEGACY_CSV", tmp_path / "leads.csv")
    bot.init_db()
    return path


def lead(**kw):
    base = {"vaqt": "2026-11-01 10:00", "ism": "Ali", "kompaniya": "X", "telefon": "+998901234567",
            "yonalish": "CRM", "username": "@ali", "chat_id": 1}
    return base | kw


def test_save_and_fetch(db):
    bot.save_lead(lead())
    bot.save_lead(lead(ism="Vali", chat_id=2))
    rows = bot.fetch_leads()
    assert [r["name"] for r in rows] == ["Ali", "Vali"]


def test_legacy_csv_imported_once(tmp_path, monkeypatch):
    csv_path = tmp_path / "leads.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=bot.LEAD_FIELDS)
        w.writeheader()
        w.writerow(lead())
    db_path = tmp_path / "leads.db"
    monkeypatch.setattr(bot, "DB_FILE", db_path)
    bot.init_db(legacy_csv=csv_path)
    bot.init_db(legacy_csv=csv_path)  # qayta ishga tushish dublikat yaratmasin
    assert len(bot.fetch_leads()) == 1


def test_csv_export_blocks_formula_injection(db):
    bot.save_lead(lead(ism='=HYPERLINK("http://evil")', kompaniya="@cmd"))
    data = bot.leads_csv_bytes(bot.fetch_leads())
    rows = list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))
    assert rows[0] == bot.LEAD_FIELDS
    assert rows[1][1].startswith("'=") and rows[1][2] == "'@cmd"
    assert rows[1][3] == "+998901234567"  # telefon o'zgarmaydi


def test_stats(db):
    bot.save_lead(lead())
    bot.save_lead(lead(chat_id=2, yonalish="ERP"))
    bot.save_lead(lead(chat_id=2, yonalish="ERP"))
    s = bot.lead_stats()
    assert s["total"] == 3 and s["unique"] == 2
    assert s["by_topic"][0] == ("ERP", 2)


def test_admin_ids(monkeypatch):
    monkeypatch.setenv("ADMIN_CHAT_ID", "123, -456 abc 789")
    assert bot.admin_ids() == {123, -456, 789}
    monkeypatch.delenv("ADMIN_CHAT_ID")
    assert bot.admin_ids() == set()


class FakeRequest(BaseRequest):
    """Telegram serverini almashtiradi: so'rovlarni yozib oladi, tayyor javob qaytaradi."""

    def __init__(self):
        self.calls = []

    @property
    def read_timeout(self):
        return 1

    async def initialize(self):
        pass

    async def shutdown(self):
        pass

    async def do_request(self, url, method, request_data=None, **kwargs):
        name = url.rsplit("/", 1)[-1]
        params = dict(request_data.parameters) if request_data else {}
        self.calls.append((name, params))
        if name == "getMe":
            result = {"id": 1, "is_bot": True, "first_name": "UstunSys", "username": "ustunsys_bot"}
        elif name in ("sendMessage", "sendDocument"):
            result = {"message_id": 1, "date": 0, "chat": {"id": params.get("chat_id", 1), "type": "private"}}
        else:
            result = True
        return 200, json.dumps({"ok": True, "result": result}).encode()

    def texts(self, chat_id):
        return [p["text"] for n, p in self.calls if n == "sendMessage" and p.get("chat_id") == chat_id]


USER = {"id": 555, "is_bot": False, "first_name": "Ali", "username": "ali"}
CHAT = {"id": 555, "type": "private"}


def msg_update(uid, text, user=USER):
    chat = {"id": user["id"], "type": "private"}
    return {"update_id": uid, "message": {"message_id": uid, "date": 0, "chat": chat,
                                          "from": user, "text": text,
                                          **({"entities": [{"type": "bot_command", "offset": 0,
                                                            "length": len(text.split()[0])}]}
                                             if text.startswith("/") else {})}}


def contact_update(uid, phone, owner_id=USER["id"]):
    return {"update_id": uid, "message": {"message_id": uid, "date": 0, "chat": CHAT, "from": USER,
                                          "contact": {"phone_number": phone, "first_name": "X",
                                                      "user_id": owner_id}}}


def edited_update(uid, text):
    return {"update_id": uid, "edited_message": {"message_id": uid, "date": 0, "edit_date": 1,
                                                 "chat": CHAT, "from": USER, "text": text}}


def test_contact_phone():
    assert bot.contact_phone("998901234567") == "+998901234567"
    assert bot.contact_phone("+79991234567") == "+79991234567"  # chet el raqami ham qabul


def cb_update(uid, data):
    return {"update_id": uid, "callback_query": {
        "id": str(uid), "from": USER, "chat_instance": "x", "data": data,
        "message": {"message_id": 1, "date": 0, "chat": CHAT}}}


def run_steps(steps):
    fake = FakeRequest()

    async def run():
        app = Application.builder().token("123:ABC").request(fake).build()
        built = bot.build_app("123:ABC")
        for h in built.handlers[0]:
            app.add_handler(h)
        await app.initialize()
        for s in steps:
            await app.process_update(Update.de_json(s, app.bot))
        await app.shutdown()

    asyncio.run(run())
    return fake


def test_full_lead_flow(db, monkeypatch):
    monkeypatch.setenv("ADMIN_CHAT_ID", "999")
    fake = run_steps([
        msg_update(1, "/start"),
        cb_update(2, "lead"),
        msg_update(3, "Ali"),
        msg_update(4, "Ustun MChJ"),
        msg_update(5, "+998 90 123 45 67"),        # qo'lda yozilgan raqam rad etiladi
        contact_update(6, "998911112233", owner_id=777),  # boshqa odamning kontakti ham
        edited_update(7, "Ali V"),                 # tahrirlangan xabar xato bermasin
        contact_update(8, "998901234567"),         # o'z raqami tugma orqali
        msg_update(9, "crm"),                      # matn yozsa, tugma so'raladi
        cb_update(10, "t_crm"),
    ])
    rows = bot.fetch_leads()
    assert len(rows) == 1
    r = rows[0]
    assert (r["name"], r["company"], r["phone"], r["topic"], r["username"]) == \
        ("Ali", "Ustun MChJ", "+998901234567", "CRM", "@ali")
    admin = fake.texts(999)
    assert len(admin) == 1 and "Ali" in admin[0]
    texts = fake.texts(555)
    assert sum("qo'lda yozmang" in t for t in texts) == 2
    assert any("tugmalardan birini" in t for t in texts)


def test_start_mid_conversation_resets_it(db):
    """Bug: /start suhbatni yopmasdi, keyingi matn 'ism' sifatida qabul qilinardi."""
    fake = run_steps([
        cb_update(1, "lead"),
        msg_update(2, "/start"),
        msg_update(3, "salom"),  # endi bu ism emas — suhbat yopilgan
    ])
    texts = fake.texts(555)
    assert "Bekor qilindi." in texts
    assert "Kompaniyangiz nomi?" not in texts


def test_lead_button_reentry(db):
    """Suhbat o'rtasida 'Bepul demo' qayta bosilsa, boshidan boshlanadi."""
    fake = run_steps([
        cb_update(1, "lead"),
        msg_update(2, "Ali"),
        cb_update(3, "lead"),
    ])
    assert fake.texts(555).count("Ismingiz nima?\n(Bekor qilish: /cancel)") == 2


def test_stale_button_is_answered(db):
    fake = run_steps([cb_update(1, "t_crm")])  # suhbatsiz eski tugma
    assert any(n == "answerCallbackQuery" for n, _ in fake.calls)
    assert bot.fetch_leads() == []


def test_export_only_for_admin(db, monkeypatch):
    monkeypatch.setenv("ADMIN_CHAT_ID", "999")
    bot.save_lead(lead())
    admin = {"id": 999, "is_bot": False, "first_name": "Boss"}
    fake = run_steps([msg_update(1, "/export"), msg_update(2, "/export", user=admin)])
    docs = [p for n, p in fake.calls if n == "sendDocument"]
    assert len(docs) == 1 and docs[0]["chat_id"] == 999


def test_skip_phone_when_enabled(db, monkeypatch):
    monkeypatch.setenv("ADMIN_CHAT_ID", "999")
    fake = run_steps([
        cb_update(1, "lead"),
        msg_update(2, "Ali"),
        msg_update(3, "Ustun"),
        msg_update(4, bot.SKIP_PHONE),
        cb_update(5, "t_erp"),
    ])
    rows = bot.fetch_leads()
    assert len(rows) == 1 and rows[0]["phone"] == ""
    admin = fake.texts(999)[0]
    assert "Telegram orqali" in admin and "tg://user?id=555" in admin


def test_skip_phone_when_disabled(db):
    bot.set_setting("skip_phone", "0")
    fake = run_steps([
        cb_update(1, "lead"),
        msg_update(2, "Ali"),
        msg_update(3, "Ustun"),
        msg_update(4, bot.SKIP_PHONE),  # eski klaviaturadan bosilsa ham o'tmaydi
    ])
    assert any("qo'lda yozmang" in t for t in fake.texts(555))
    kb = [p["reply_markup"] for n, p in fake.calls if n == "sendMessage" and "reply_markup" in p]
    assert not any(bot.SKIP_PHONE in str(k) for k in kb)


def test_toggle_only_by_admin(db, monkeypatch):
    monkeypatch.setenv("ADMIN_CHAT_ID", "999")
    run_steps([cb_update(1, "cfg_skip_phone")])  # USER (555) admin emas
    assert bot.skip_phone_enabled() is True
    admin_cb = cb_update(2, "cfg_skip_phone")
    admin_cb["callback_query"]["from"] = {"id": 999, "is_bot": False, "first_name": "Boss"}
    run_steps([admin_cb])
    assert bot.skip_phone_enabled() is False


def test_migration_from_v1(tmp_path, monkeypatch):
    import sqlite3
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as conn:  # 1-versiyadagi baza: settings jadvali yo'q
        conn.execute("CREATE TABLE leads (id INTEGER PRIMARY KEY, created_at TEXT NOT NULL,"
                     " name TEXT NOT NULL, company TEXT NOT NULL, phone TEXT NOT NULL,"
                     " topic TEXT NOT NULL, username TEXT NOT NULL DEFAULT '', chat_id INTEGER NOT NULL)")
        conn.execute("PRAGMA user_version=1")
    monkeypatch.setattr(bot, "DB_FILE", path)
    bot.init_db(legacy_csv=tmp_path / "none.csv")
    bot.set_setting("skip_phone", "0")
    assert bot.skip_phone_enabled() is False
