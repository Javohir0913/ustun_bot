#!/usr/bin/env bash
# ADMIN uchun (to'liq sudo): kodni yangilaydi, servis faylini va ustun-bot buyrug'ini
# qayta o'rnatadi. Ishlatish: sudo bash /opt/ustun_bot/deploy/update.sh
set -euo pipefail
DIR=/opt/ustun_bot
sudo -u ustunbot git -C "$DIR" pull --ff-only
sudo -u ustunbot "$DIR/.venv/bin/pip" install -q -r "$DIR/requirements.txt"
install -m 644 -o root -g root "$DIR/deploy/ustun-bot.service" /etc/systemd/system/ustun-bot.service
install -m 755 -o root -g root "$DIR/deploy/ustun-bot" /usr/local/bin/ustun-bot
systemctl daemon-reload
systemctl restart ustun-bot
sleep 3
systemctl --no-pager --lines=5 status ustun-bot
