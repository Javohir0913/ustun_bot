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

## Jamoa a'zolari (masalan `abdurahim`)
`ustunbot` guruhidagilar `/opt/ustun_bot` dagi hamma narsani (kod, `.env`, `leads.db`) ko'radi va
o'zgartiradi, botni esa faqat shu buyruq bilan boshqaradi (to'liq sudo yo'q):
```
sudo ustun-bot status      # holat
sudo ustun-bot restart     # qayta ishga tushirish
sudo ustun-bot logs 200    # oxirgi 200 qator log
sudo ustun-bot follow      # jonli log (Ctrl+C)
sudo ustun-bot update      # GitHub'dan git pull + restart
```
Kirish: `ssh abdurahim@20.84.45.45` (o'z kaliti bilan), papka: `cd /opt/ustun_bot`.

## Yangi odamga ruxsat berish (azureuser nomidan)
Misol: `vali` ga `/opt/ustun_bot` ga ruxsat.
```
# 1. Foydalanuvchi (nom faqat kichik harf/raqam) va uning OCHIQ kaliti (.pub ichidagi bitta qator)
sudo useradd -m -s /bin/bash vali
sudo install -d -m 700 -o vali -g vali /home/vali/.ssh
echo 'ssh-ed25519 AAAA... vali' | sudo tee /home/vali/.ssh/authorized_keys
sudo chown vali:vali /home/vali/.ssh/authorized_keys && sudo chmod 600 /home/vali/.ssh/authorized_keys

# 2. Papka guruhiga qo'shish (ruxsat shu guruh orqali beriladi)
sudo usermod -aG ustunbot vali
echo 'umask 002' | sudo tee -a /home/vali/.profile /home/vali/.bashrc   # yaratgan fayllari guruhga ochiq bo'lsin
sudo -u vali git config --global --add safe.directory /opt/ustun_bot
```
Kirish keyingi ulanishda ishlaydi (guruh login paytida o'qiladi).

**Boshqa papkaga ruxsat** (masalan `/opt/yangi_loyiha`) — o'sha papka uchun guruh ochib, ichiga odamni qo'shasiz:
```
sudo groupadd yangi_loyiha
sudo chgrp -R yangi_loyiha /opt/yangi_loyiha
sudo chmod -R g+rwX,o-rwx /opt/yangi_loyiha                  # guruh: o'qish+yozish, boshqalar: yo'q
sudo find /opt/yangi_loyiha -type d -exec chmod g+s {} +     # yangi fayllar ham shu guruhda bo'lsin
sudo usermod -aG yangi_loyiha vali
```
Faqat ko'rish (o'zgartirmasin) kerak bo'lsa: `g+rwX` o'rniga `g+rX`.

**Ruxsatni olib tashlash:** `sudo gpasswd -d vali ustunbot` (bitta papkadan),
butunlay: `sudo userdel -r vali`. Tekshirish: `id vali`, `ls -la /opt`.

Hech qachon `azureuser` kalitini (`.pem`) boshqalarga bermang: u bilan butun serverga va sudo'ga kiriladi.

## Muhim
- Bir token bilan faqat BITTA joyda bot ishlasin. Server ishlayotganda kompyuterdagi `run_bot.bat` ni ishga tushirmang, aks holda ikkalasi to'qnashadi (`Conflict: terminated by other getUpdates`).
