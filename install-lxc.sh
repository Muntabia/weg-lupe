#!/usr/bin/env bash
# Installiert WEG-Lupe in einem Debian-Container (wird vom Proxmox-Skript automatisch aufgerufen).
# Manuell: Repo nach /opt/weg-lupe klonen und als root  /opt/weg-lupe/install-lxc.sh  ausführen.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR=/var/lib/weg-lupe
SERVICE=weg-lupe
PORT="${PORT:-8080}"

echo "==> Pakete installieren"
apt-get update -qq
apt-get install -y -qq git python3 python3-venv tesseract-ocr tesseract-ocr-deu tesseract-ocr-eng ca-certificates >/dev/null

echo "==> Benutzer und Ordner"
id weglupe >/dev/null 2>&1 || useradd --system --home "$DATA_DIR" --shell /usr/sbin/nologin weglupe
mkdir -p "$DATA_DIR"
chown -R weglupe:weglupe "$DATA_DIR"

echo "==> Python-Umgebung"
[ -d "$APP_DIR/venv" ] || python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install -q --upgrade pip
"$APP_DIR/venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"

echo "==> Dienst einrichten"
cat > /etc/systemd/system/$SERVICE.service <<UNIT
[Unit]
Description=WEG-Lupe
After=network-online.target
Wants=network-online.target

[Service]
User=weglupe
WorkingDirectory=$APP_DIR
Environment=DATA_DIR=$DATA_DIR
ExecStart=$APP_DIR/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port $PORT
Restart=on-failure
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
UNIT

cat > /usr/local/bin/weglupe-update <<EOF
#!/usr/bin/env bash
# WEG-Lupe auf den neuesten Stand bringen
set -euo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
git -C "$APP_DIR" pull --ff-only
# Installationsskript erneut ausführen: aktualisiert Pakete, Dienst und diese Hilfsbefehle
PORT=$PORT bash "$APP_DIR/install-lxc.sh"
echo "WEG-Lupe aktualisiert: \$(git -C "$APP_DIR" log -1 --format='%h %s')"
EOF

cat > /usr/local/bin/weglupe-reset-password <<EOF
#!/usr/bin/env bash
# Ohne Argument: Passwort entfernen. Mit Argument: neues Passwort setzen (Benutzer: weg).
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
cd "$APP_DIR"
exec runuser -u weglupe -- env DATA_DIR=$DATA_DIR "$APP_DIR/venv/bin/python" -m app.reset_password "\${1:-}"
EOF
chmod +x /usr/local/bin/weglupe-update /usr/local/bin/weglupe-reset-password

systemctl daemon-reload
systemctl enable --now $SERVICE >/dev/null 2>&1
systemctl restart $SERVICE

for _ in $(seq 1 30); do
  if python3 -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:$PORT/healthz',timeout=2)" 2>/dev/null; then
    echo "==> WEG-Lupe läuft auf Port $PORT"
    exit 0
  fi
  sleep 1
done
echo "WEG-Lupe startet nicht. Log: journalctl -u $SERVICE -n 50" >&2
exit 1
