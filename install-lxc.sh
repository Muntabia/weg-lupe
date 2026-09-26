#!/usr/bin/env bash
# Installation ohne Docker in einem Debian-12/13-LXC auf Proxmox. Als root ausführen.
set -euo pipefail
APP_DIR=/opt/weglupe
apt-get update
apt-get install -y python3 python3-venv tesseract-ocr tesseract-ocr-deu
id weglupe >/dev/null 2>&1 || useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin weglupe
mkdir -p "$APP_DIR" /var/lib/weglupe
cp -r app requirements.txt "$APP_DIR"/
[ -f "$APP_DIR/.env" ] || cp .env.example "$APP_DIR/.env"
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --upgrade pip
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"
chown -R weglupe:weglupe "$APP_DIR" /var/lib/weglupe
cat > /etc/systemd/system/weglupe.service <<UNIT
[Unit]
Description=WEG-Lupe
After=network-online.target

[Service]
User=weglupe
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
Environment=DATA_DIR=/var/lib/weglupe
ExecStart=$APP_DIR/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8080
Restart=on-failure

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now weglupe
echo "Fertig. WEG-Lupe läuft auf http://$(hostname -I | awk '{print $1}'):8080"
echo "Einstellungen: $APP_DIR/.env bearbeiten, danach: systemctl restart weglupe"
