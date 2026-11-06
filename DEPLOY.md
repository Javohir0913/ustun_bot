# Serverda ishlatish (Ubuntu 24.04, GitHub orqali)

Kod: https://github.com/Javohir0913/ustun_bot
Server: `/opt/ustun_bot`, servis nomi `ustun-bot`, alohida `ustunbot` foydalanuvchisi nomidan ishlaydi.

`.env`, `leads.csv`, `leads.db` GitHub'ga YUKLANMAYDI (`.gitignore`). Ular faqat serverda turadi.

## Kodni yangilash
1. Kompyuterda o'zgartiring va GitHub'ga yuboring:
```
git add -A
git commit -m "nima o'zgardi"
git push
```
2. Serverda:
```
ssh -i "C:\Users\pro10\Downloads\ubuntu-server-2_key.pem" azureuser@20.84.45.45
sudo bash /opt/ustun_bot/deploy/update.sh
```

## Kerakli buyruqlar (serverda)
- Holat: `sudo systemctl status ustun-bot`
- Loglar: `sudo journalctl -u ustun-bot -f`
- Qayta ishga tushirish: `sudo systemctl restart ustun-bot`
- `.env` ni o'zgartirish: `sudo nano /opt/ustun_bot/.env`, keyin restart
- Bazani kompyuterga olish (zaxira): `scp -i "...pem" azureuser@20.84.45.45:/opt/ustun_bot/leads.db .`
  (yoki botda `/export`)

## Birinchi o'rnatish (bir marta qilingan)
```
sudo apt install -y python3-venv git
sudo useradd --system --home /opt/ustun_bot --shell /usr/sbin/nologin ustunbot
sudo git clone https://github.com/Javohir0913/ustun_bot /opt/ustun_bot
sudo chown -R ustunbot:ustunbot /opt/ustun_bot
sudo -u ustunbot python3 -m venv /opt/ustun_bot/.venv
sudo -u ustunbot /opt/ustun_bot/.venv/bin/pip install -r /opt/ustun_bot/requirements.txt
# .env (va eski so'rovlar uchun leads.csv) kompyuterdan scp bilan yuboriladi, chmod 600
sudo install -m 644 /opt/ustun_bot/deploy/ustun-bot.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now ustun-bot
```

## Muhim
- Bir token bilan faqat BITTA joyda bot ishlasin. Server ishlayotganda kompyuterdagi `run_bot.bat` ni ishga tushirmang, aks holda ikkalasi to'qnashadi (`Conflict: terminated by other getUpdates`).
