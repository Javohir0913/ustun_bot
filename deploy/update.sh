#!/usr/bin/env bash
# Serverda yangi kodni GitHub'dan olib, botni qayta ishga tushiradi.
# Ishlatish: sudo bash /opt/ustun_bot/deploy/update.sh
set -euo pipefail
DIR=/opt/ustun_bot
sudo -u ustunbot git -C "$DIR" pull --ff-only
sudo -u ustunbot "$DIR/.venv/bin/pip" install -q -r "$DIR/requirements.txt"
install -m 644 "$DIR/deploy/ustun-bot.service" /etc/systemd/system/ustun-bot.service
systemctl daemon-reload
systemctl restart ustun-bot
sleep 3
systemctl --no-pager --lines=5 status ustun-bot
