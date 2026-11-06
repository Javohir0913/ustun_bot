# UstunSys Telegram bot

Instagram bio'dagi havola shu botga olib keladi. Bot xizmatlarni ko'rsatadi, narx haqida javob beradi va **bepul demo / mini-audit** uchun so'rov yig'adi (ism, kompaniya, telefon, yo'nalish). Har bir so'rov sizga Telegramga xabar sifatida keladi va `leads.db` (SQLite) bazasiga yoziladi.

## Baza va admin buyruqlari
- So'rovlar `leads.db` faylida saqlanadi. Eski `leads.csv` birinchi ishga tushishda bazaga avtomatik ko'chiriladi (bir marta), fayl o'zi o'chirilmaydi.
- `/export` — barcha so'rovlarni Excel'da ochiladigan CSV fayl qilib yuboradi.
- `/stats` — jami, bugungi, 7 kunlik so'rovlar va yo'nalishlar bo'yicha son.
- `/sozlamalar` — "Raqamsiz davom etish" tugmasini yoqish/o'chirish (standart: yoqilgan). Raqamsiz so'rovda sizga mijoz profiliga havola keladi, unga Telegramda yozasiz.
- Bu buyruqlar faqat `ADMIN_CHAT_ID` dagi odamlarga ishlaydi.
- Zaxira nusxa: bot to'xtagan paytda `leads.db` ni ko'chirib qo'ying (yoki `/export`).

## 1. Bot yaratish (sizning ishingiz, 2 daqiqa)
1. Telegramda **@BotFather** ni oching → `/newbot`.
2. Nom: `UstunSys`. Username: `ustunsys_bot` (band bo'lsa `ustunsys_uz_bot` kabi, oxiri `bot` bilan tugashi shart).
3. BotFather **token** beradi (`123456:ABC...`). Uni hech kimga va hech qaysi chatga yozmang.
4. Xohlasangiz: BotFather → `/setdescription`, `/setabouttext`, `/setuserpic` (logotip).

## 2. Sozlash
1. `.env.example` faylidan nusxa olib, nomini `.env` qiling.
2. Ichiga yozing:
```
BOT_TOKEN=BotFather bergan token
ADMIN_CHAT_ID=
```
3. `run_bot.bat` ni ikki marta bosib ishga tushiring.
4. Telegramda o'z botingizga `/myid` yozing: u chat ID raqamingizni qaytaradi (masalan `123456789`).
5. Botni to'xtating (Ctrl+C), `.env` dagi `ADMIN_CHAT_ID=` ga shu raqamni yozing, qayta ishga tushiring.
   Bir nechta odam xabar olsin desangiz, raqamlarni vergul bilan yozing: `111,222`.

## 3. Instagram bio'ga qo'yish
Havola: `https://t.me/<bot_username>` (masalan `https://t.me/ustunsys_bot`).
Instagram ilovasida: Profil → Редактировать профиль → **Ссылки** → Добавить ссылку.

## 4. Tekshirish
Botga `/start` yozing → "Bepul demo / mini-audit" → hamma savolga javob bering. Sizga xabar kelishi kerak, `/stats` esa so'rov sonini ko'rsatadi.

## Muhim
- Bot **kompyuteringiz yoqiq va `run_bot.bat` ochiq turganda** ishlaydi. Kompyuter o'chsa, bot javob bermaydi. Doimiy ishlashi uchun uni serverga (VPS) ko'chirish kerak. Buni keyin birga qilamiz.
- `.env` faylida token bor: uni boshqalarga yubormang.
- Telefon raqamlari shaxsiy ma'lumot. `leads.db` va `leads.csv` ni faqat o'zingiz saqlang.
- `.venv` papkasini boshqa kompyuterga ko'chirmang: `run_bot.bat` uni kerak bo'lsa o'zi qayta yaratadi.
- Matnlarni o'zgartirish uchun `bot.py` boshidagi `WELCOME`, `SERVICES`, `PRICE`, `CONTACT` qatorlarini tahrirlang.

## Testlar
```
.venv\Scripts\python.exe -m pytest -q
```
