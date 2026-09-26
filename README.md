# WEG-Lupe

WEG-Unterlagen prüfen, bevor man eine Eigentumswohnung kauft.

Lade die Protokolle der Eigentümerversammlungen, Wirtschaftspläne, Jahresabrechnungen und die Beschlusssammlung hoch. WEG-Lupe markiert, was einen Käufer Geld kosten kann: Sonderumlagen, Sanierungsstau, Schäden, Hausgeldrückstände, Streit, Anfechtungsklagen, Verwalterwechsel und Themen, die immer wieder vertagt werden. Zu jedem Treffer gibt es die Fundstelle mit Seitenzahl und einen Link direkt auf die PDF-Seite.

> Hinweis: WEG-Lupe ist eine Lesehilfe. Sie ersetzt keine Rechts-, Steuer- oder Bausachverständigen-Beratung. Prüfe jeden Befund anhand der verlinkten Seite.

## Was die Anwendung kann

- **Stichwort-Prüfung ohne KI:** rund 50 Regeln in 9 Kategorien. Erkennt Verneinungen („keine Sonderumlage erforderlich“ wird nur als Info gezeigt) und ordnet Beträge im selben Satz zu. Das läuft komplett lokal und kostet nichts.
- **Texterkennung für Scans:** Seiten ohne Textebene werden automatisch mit Tesseract (Deutsch) gelesen.
- **KI-Analyse (optional):** Claude über die Anthropic-API oder ein lokales Modell über jede OpenAI-kompatible Schnittstelle (Ollama, LM Studio, vLLM). Die KI muss jeden Befund mit einem wörtlichen Zitat belegen. WEG-Lupe prüft das Zitat gegen den Dokumenttext, korrigiert falsche Seitenangaben und markiert erfundene Zitate mit „Zitat nicht gefunden“.
- **Einschätzung:** Die KI schreibt eine Zusammenfassung mit den größten Kostenrisiken und Fragen an Verkäufer oder Verwaltung für den Notartermin.
- **Kennzahlen:** Findet Werte zur Erhaltungsrücklage und zum Hausgeld. Du bestätigst den richtigen Wert, WEG-Lupe rechnet ihn auf €/m² und deinen Anteil nach Miteigentumsanteil um.
- **Checkliste:** Zeigt, welche Unterlagen für eine vollständige Prüfung noch fehlen.
- **Volltextsuche** über alle Unterlagen eines Objekts.
- **Bericht** als druckbare HTML-Seite (im Browser als PDF speichern).

## Installation auf Proxmox

Das Repository ist privat. Deshalb holt sich der Container den Code über einen eigenen **Deploy Key**: einen SSH-Schlüssel, der nur dieses eine Repository lesen darf. Das Skript erzeugt ihn und zeigt ihn während der Installation an.

**1. Skript auf den Proxmox-Host kopieren** (von Windows aus, in PowerShell):

```powershell
scp C:\Users\julia\Projekte\WEG-Lupe\proxmox\weg-lupe-lxc.sh root@<proxmox-ip>:/root/
```

**2. Auf dem Proxmox-Host als root ausführen** (Shell im Webinterface oder per SSH):

```bash
bash /root/weg-lupe-lxc.sh
```

Das Skript
- nimmt die nächste freie Container-ID und den ersten passenden Speicher,
- lädt die aktuelle Debian-Vorlage und legt einen unprivilegierten LXC an (2 Kerne, 2 GB RAM, 10 GB, DHCP an `vmbr0`),
- erzeugt im Container einen Deploy Key und prüft GitHubs Hostschlüssel gegen den offiziellen Fingerabdruck,
- **hält an und zeigt den Key an.** Du öffnest den angezeigten Link (GitHub → Repo → Settings → Deploy keys → Add deploy key), fügst den Key ein, lässt „Allow write access“ **aus** und drückst im Terminal Enter,
- klont das Repo und installiert WEG-Lupe mit Texterkennung als Dienst, der beim Booten startet,
- erzeugt ein zufälliges Passwort und zeigt am Ende Adresse, Benutzer und Passwort an.

Andere Werte lassen sich vorab setzen, zum Beispiel:

```bash
CTID=150 RAM=4096 STORAGE=local-zfs IP=192.168.1.60/24 GATEWAY=192.168.1.1 bash /root/weg-lupe-lxc.sh
```

Mögliche Variablen: `CTID`, `CT_HOSTNAME`, `CORES`, `RAM`, `SWAP`, `DISK`, `STORAGE`, `TEMPLATE_STORAGE`, `BRIDGE`, `IP`, `GATEWAY`, `PORT`, `REPO_URL`, `BRANCH`.

Wird das Repository später öffentlich, geht es auch ohne Deploy Key und ohne Kopieren:

```bash
REPO_URL=https://github.com/Muntabia/weg-lupe.git \
  bash -c "$(curl -fsSL https://raw.githubusercontent.com/Muntabia/weg-lupe/main/proxmox/weg-lupe-lxc.sh)"
```

### Befehle auf dem Proxmox-Host

| Zweck | Befehl |
|---|---|
| Auf neue Version aktualisieren (nach `git push`) | `pct exec <ID> -- weglupe-update` |
| Passwort entfernen (ausgesperrt) | `pct exec <ID> -- weglupe-reset-password` |
| Neues Passwort setzen | `pct exec <ID> -- weglupe-reset-password NEUES_PASSWORT` |
| Log ansehen | `pct exec <ID> -- journalctl -u weg-lupe -f` |
| Backup | `vzdump <ID>` oder im Proxmox-Webinterface |

Die Daten liegen im Container unter `/var/lib/weg-lupe`.

### Alternative: Docker

```bash
docker compose up -d --build
```

Die Daten liegen dann in `./data`.

## Einstellungen

Alles wird in der App eingestellt, über das Zahnrad oben rechts. Eine `.env`-Datei ist nicht nötig.

- **KI-Analyse:** Aus, Claude (Anthropic) oder ein lokales Modell über eine OpenAI-kompatible Schnittstelle (Ollama, LM Studio, vLLM). Mit „Modelle laden“ holst du die verfügbaren Modelle, mit „Verbindung testen“ prüfst du Adresse und Key. API-Keys werden nach dem Speichern nie wieder angezeigt, nur die letzten vier Zeichen.
- **Zugang:** Benutzername und Passwort (HTTP-Basic-Auth, Passwort als PBKDF2-Hash gespeichert).
- **Texterkennung:** Sprache, Auflösung und maximale Dateigröße.

Für Docker-Nutzer: Umgebungsvariablen wie `LLM_PROVIDER`, `ANTHROPIC_API_KEY`, `OPENAI_BASE_URL` oder `APP_PASSWORD` werden als Startwerte gelesen, solange in der App nichts gespeichert ist.

### Welche KI?

- **Anthropic (Claude):** die beste Erkennung. Die Unterlagen gehen dabei an die API. WEG-Protokolle enthalten Namen und teils Zahlungsrückstände anderer Eigentümer, das solltest du bedenken. Eine typische Prüfung mit 100–200 Seiten kostet grob einige Cent bis wenige Euro, je nach Modell.
- **Lokal mit Ollama:** Die Daten bleiben bei dir, es kostet nichts. Dafür ist die Erkennung schwächer und es braucht ordentlich Hardware (für ein 14B-Modell etwa 16 GB RAM, mit GPU deutlich schneller). Ollama kann in einem eigenen LXC auf demselben Proxmox laufen. Adresse in den Einstellungen dann z. B. `http://192.168.1.50:11434/v1`.
- **Ohne KI:** Die Stichwort-Prüfung findet die meisten Warnsignale, erzeugt aber mehr Treffer, die du selbst sortieren musst.

## Sicherheit

Die Anwendung ist für dein Heimnetz gedacht. Stell sie nicht ungeschützt ins Internet. Für Zugriff von unterwegs nutze ein VPN (WireGuard, Tailscale) oder einen Reverse Proxy mit HTTPS. Ohne HTTPS geht das Passwort im Klartext durchs Netz, im eigenen LAN ist das meist vertretbar.

## Entwicklung

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt pytest
sudo apt install tesseract-ocr tesseract-ocr-deu
DATA_DIR=./data uvicorn app.main:app --reload --port 8080
python -m pytest tests
python samples/make_samples.py   # fiktive Beispielunterlagen erzeugen
```

Aufbau:

- `app/rules.py`: Stichwort-Regeln, Betrags- und Kennzahlenerkennung. Neue Regeln einfach in `RULES` ergänzen.
- `app/extract.py`: PDF-Text und Texterkennung
- `app/llm.py`: KI-Anbindung und Prompts
- `app/settings.py`: Einstellungen in der Datenbank, Passwort-Hashing
- `proxmox/weg-lupe-lxc.sh`: Installation auf Proxmox, `install-lxc.sh`: Einrichtung im Container
- `app/analyze.py`: Verarbeitung im Hintergrund, Zitatprüfung, Zusammenfassung
- `app/main.py`: Web-API und Bericht
- `app/static/`: Oberfläche ohne Framework und ohne Build-Schritt

## Lizenz

MIT
