#!/usr/bin/env bash
# WEG-Lupe auf Proxmox VE installieren: legt einen Debian-LXC an und richtet alles ein.
#
# Skript auf den Proxmox-Host kopieren und dort als root ausführen:
#   bash weg-lupe-lxc.sh
#
# Das Repository ist privat. Der Container bekommt deshalb einen eigenen, schreibgeschützten
# Deploy Key. Das Skript zeigt ihn während der Installation an; du trägst ihn einmal auf GitHub ein.
#
# Standardwerte lassen sich per Umgebungsvariable überschreiben, z. B.:
#   CTID=150 RAM=4096 STORAGE=local-zfs BRIDGE=vmbr1 bash weg-lupe-lxc.sh
# Ist das Repository öffentlich, geht es auch ohne Deploy Key:
#   REPO_URL=https://github.com/Muntabia/weg-lupe.git bash weg-lupe-lxc.sh
set -euo pipefail

REPO_URL="${REPO_URL:-git@github.com:Muntabia/weg-lupe.git}"
BRANCH="${BRANCH:-main}"
CT_HOSTNAME="${CT_HOSTNAME:-weg-lupe}"
CORES="${CORES:-2}"
RAM="${RAM:-2048}"
SWAP="${SWAP:-512}"
DISK="${DISK:-10}"
BRIDGE="${BRIDGE:-vmbr0}"
IP="${IP:-dhcp}"            # oder z. B. 192.168.1.60/24
GATEWAY="${GATEWAY:-}"      # nur bei fester IP nötig
PORT="${PORT:-8080}"

c_ok() { printf '\e[32m%s\e[0m\n' "$*"; }
c_info() { printf '\e[36m==> %s\e[0m\n' "$*"; }
die() { printf '\e[31mFehler: %s\e[0m\n' "$*" >&2; on_error; exit 1; }

[ "$(id -u)" -eq 0 ] || die "Bitte als root auf dem Proxmox-Host ausführen."
command -v pct >/dev/null || die "pct nicht gefunden. Das Skript muss auf dem Proxmox-Host laufen, nicht in einem Container."

USE_SSH=0
case "$REPO_URL" in git@*|ssh://*) USE_SSH=1 ;; esac
if [ "$USE_SSH" -eq 1 ] && ! { : </dev/tty; } 2>/dev/null; then
  die "Für den Deploy Key muss das Skript interaktiv in einer Shell laufen."
fi
# GitHubs veröffentlichter Ed25519-Hostschlüssel (docs.github.com, "GitHub's SSH key fingerprints")
GITHUB_ED25519_FP="SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU"
CREATED=0
on_error() {
  if [ "$CREATED" -eq 1 ]; then
    printf '\n\e[33mDer Container %s bleibt zur Fehlersuche bestehen. Entfernen mit: pct stop %s; pct destroy %s --purge\e[0m\n' "$CTID" "$CTID" "$CTID" >&2
  fi
}
trap on_error ERR

CTID="${CTID:-$(pvesh get /cluster/nextid)}"
pct status "$CTID" >/dev/null 2>&1 && die "Container-ID $CTID ist schon vergeben. Andere ID mit CTID=... wählen."

STORAGE="${STORAGE:-$(pvesm status -content rootdir 2>/dev/null | awk 'NR>1 && $3=="active" && !f {print $1; f=1}')}"
[ -n "$STORAGE" ] || die "Kein Speicher für Container gefunden. Mit STORAGE=... angeben."
TSTORAGE="${TEMPLATE_STORAGE:-$(pvesm status -content vztmpl 2>/dev/null | awk 'NR>1 && $3=="active" && !f {print $1; f=1}')}"
[ -n "$TSTORAGE" ] || die "Kein Speicher für Vorlagen (vztmpl) gefunden. Mit TEMPLATE_STORAGE=... angeben."

c_info "Suche Debian-Vorlage"
pveam update >/dev/null 2>&1 || true
TEMPLATE="$(pveam available --section system 2>/dev/null | awk '$2 ~ /^debian-13-standard/ {print $2}' | sort -V | tail -1)"
[ -n "$TEMPLATE" ] || TEMPLATE="$(pveam available --section system 2>/dev/null | awk '$2 ~ /^debian-12-standard/ {print $2}' | sort -V | tail -1)"
[ -n "$TEMPLATE" ] || die "Keine Debian-Vorlage gefunden. Internetverbindung des Hosts prüfen."

NET="name=eth0,bridge=$BRIDGE,ip=$IP"
[ -n "$GATEWAY" ] && NET="$NET,gw=$GATEWAY"

cat <<EOF

  WEG-Lupe wird mit diesen Werten installiert:
    Container-ID   $CTID
    Hostname       $CT_HOSTNAME
    Vorlage        $TEMPLATE
    Speicher       $STORAGE (${DISK} GB)
    CPU / RAM      $CORES Kerne / $RAM MB
    Netzwerk       $BRIDGE, IP: $IP
    Quelle         $REPO_URL ($BRANCH)

EOF
if [ -t 0 ] || [ -e /dev/tty ]; then
  read -r -p "Fortfahren? [J/n] " answer </dev/tty || answer=""
  case "${answer,,}" in n|nein) echo "Abgebrochen."; exit 0 ;; esac
fi

if ! pveam list "$TSTORAGE" 2>/dev/null | grep -F "$TEMPLATE" >/dev/null; then
  c_info "Lade Vorlage $TEMPLATE"
  pveam download "$TSTORAGE" "$TEMPLATE" >/dev/null
fi

c_info "Lege Container $CTID an"
pct create "$CTID" "$TSTORAGE:vztmpl/$TEMPLATE" \
  --hostname "$CT_HOSTNAME" --cores "$CORES" --memory "$RAM" --swap "$SWAP" \
  --rootfs "$STORAGE:$DISK" --net0 "$NET" \
  --unprivileged 1 --features nesting=1 --onboot 1 \
  --description "WEG-Lupe: WEG-Unterlagen prüfen. Oberfläche auf Port $PORT." >/dev/null
CREATED=1
pct start "$CTID"

c_info "Warte auf Netzwerk"
for i in $(seq 1 60); do
  if pct exec "$CTID" -- getent hosts deb.debian.org >/dev/null 2>&1; then break; fi
  [ "$i" -eq 60 ] && die "Container $CTID hat kein Internet. Netzwerk/Bridge prüfen."
  sleep 2
done

c_info "Grundpakete im Container"
pct exec "$CTID" -- env LANG=C.UTF-8 DEBIAN_FRONTEND=noninteractive bash -c \
  "apt-get update -qq && apt-get install -y -qq git openssh-client ca-certificates >/dev/null" \
  || die "Paketinstallation im Container fehlgeschlagen."

if [ "$USE_SSH" -eq 1 ]; then
  c_info "Deploy Key für GitHub erzeugen"
  SETUP="$(mktemp)"
  cat > "$SETUP" <<'EOS'
set -euo pipefail
install -d -m 700 /root/.ssh
KEY=/root/.ssh/weg-lupe_deploy
[ -f "$KEY" ] || ssh-keygen -q -t ed25519 -N "" -C "weg-lupe@$(hostname)" -f "$KEY"
ssh-keyscan -t ed25519 github.com 2>/dev/null > /tmp/github_hostkey
FP="$(ssh-keygen -lf /tmp/github_hostkey | awk '{print $2}')"
if [ "$FP" != "$1" ]; then
  echo "GitHub-Hostschlüssel stimmt nicht: $FP (erwartet $1). Abbruch." >&2
  exit 3
fi
touch /root/.ssh/known_hosts
grep -qF "$(cut -d' ' -f2- /tmp/github_hostkey)" /root/.ssh/known_hosts || cat /tmp/github_hostkey >> /root/.ssh/known_hosts
cat > /root/.ssh/config <<CFG
Host github.com
  User git
  IdentityFile $KEY
  IdentitiesOnly yes
  StrictHostKeyChecking yes
CFG
chmod 600 /root/.ssh/config /root/.ssh/known_hosts
EOS
  pct push "$CTID" "$SETUP" /root/weg-lupe-ssh-setup.sh
  rm -f "$SETUP"
  pct exec "$CTID" -- bash /root/weg-lupe-ssh-setup.sh "$GITHUB_ED25519_FP" || die "SSH-Einrichtung fehlgeschlagen."
  pct exec "$CTID" -- rm -f /root/weg-lupe-ssh-setup.sh
  PUBKEY="$(pct exec "$CTID" -- cat /root/.ssh/weg-lupe_deploy.pub)"
  REPO_PATH="$(printf '%s' "$REPO_URL" | sed -E 's#^(git@github\.com:|ssh://git@github\.com/)##; s#\.git$##')"

  cat <<EOF

  ----------------------------------------------------------------------
  Jetzt einmalig den Deploy Key auf GitHub eintragen:

  1. Öffne  https://github.com/$REPO_PATH/settings/keys/new
  2. Title:  Proxmox $CT_HOSTNAME (CT $CTID)
  3. Key:    die folgende Zeile komplett kopieren

$PUBKEY

  4. "Allow write access" NICHT ankreuzen, dann "Add key".
  ----------------------------------------------------------------------

EOF
  while true; do
    read -r -p "Enter drücken, sobald der Key eingetragen ist (a = abbrechen): " answer </dev/tty || answer="a"
    case "${answer,,}" in a|abbrechen) die "Abgebrochen." ;; esac
    if pct exec "$CTID" -- git ls-remote --heads "$REPO_URL" >/dev/null 2>&1; then
      c_ok "Zugriff auf GitHub klappt."
      break
    fi
    echo "GitHub lehnt den Zugriff noch ab. Key richtig und vollständig eingetragen? Nochmal versuchen."
  done
fi

c_info "Installiere WEG-Lupe im Container (dauert 2–5 Minuten)"
pct exec "$CTID" -- env LANG=C.UTF-8 DEBIAN_FRONTEND=noninteractive bash -c "
  set -e
  git clone -q --branch '$BRANCH' '$REPO_URL' /opt/weg-lupe
  PORT='$PORT' bash /opt/weg-lupe/install-lxc.sh
" || die "Installation im Container fehlgeschlagen. Details: pct enter $CTID, dann journalctl -u weg-lupe"

PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(12))')"
pct exec "$CTID" -- weglupe-reset-password "$PASSWORD" >/dev/null

CT_IP="$(pct exec "$CTID" -- hostname -I | awk '{print $1}')"

echo
c_ok "WEG-Lupe ist installiert."
cat <<EOF

  Adresse:        http://$CT_IP:$PORT
  Benutzer:       weg
  Passwort:       $PASSWORD
                  (Jetzt notieren. Ändern kannst du es in der App unter Einstellungen.)

  KI einrichten:  In der App oben rechts auf das Zahnrad klicken.

  Nützliche Befehle auf dem Proxmox-Host:
    Aktualisieren:       pct exec $CTID -- weglupe-update   (nach jedem git push)
    Passwort entfernen:  pct exec $CTID -- weglupe-reset-password
    Log ansehen:         pct exec $CTID -- journalctl -u weg-lupe -f
    Backup:              vzdump $CTID

EOF
