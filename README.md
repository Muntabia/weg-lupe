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

### Variante A: Docker (in einem LXC mit Docker oder in einer VM)

```bash
git clone <dein-repo> weglupe && cd weglupe   # oder ZIP entpacken
cp .env.example .env                            # Einstellungen anpassen, siehe unten
docker compose up -d --build
```

Danach ist die Anwendung unter `http://<IP-des-Containers>:8080` erreichbar. Die Daten liegen in `./data`.

### Variante B: Debian-LXC ohne Docker

1. In Proxmox einen Debian-12- oder -13-LXC anlegen (1–2 Kerne, 2 GB RAM, 10 GB Speicher reichen).
2. Den Projektordner in den Container kopieren, z. B. mit `scp -r weglupe root@<ip>:/root/`.
3. Im Container:

```bash
cd /root/weglupe
./install-lxc.sh
nano /opt/weglupe/.env        # KI und Passwort einstellen
systemctl restart weglupe
```

Die Daten liegen dann in `/var/lib/weglupe`. Logs: `journalctl -u weglupe -f`.

## Einstellungen (`.env`)

| Variable | Bedeutung |
|---|---|
| `LLM_PROVIDER` | `none` (nur Stichworte), `anthropic` oder `openai` (jede OpenAI-kompatible API) |
| `ANTHROPIC_API_KEY` | API-Key für Claude, wenn `anthropic` |
| `OPENAI_BASE_URL` | z. B. `http://192.168.1.50:11434/v1` für Ollama |
| `LLM_MODEL` | Modellname. Standard: `claude-sonnet-5` bzw. `qwen2.5:14b` |
| `LLM_CHUNK_CHARS` | Zeichen pro KI-Abschnitt. Für lokale Modelle mit kleinem Kontext auf 8000 senken |
| `APP_USER` / `APP_PASSWORD` | Einfacher Passwortschutz. Leer = kein Schutz |
| `OCR_LANG`, `OCR_DPI` | Sprache und Auflösung der Texterkennung |
| `MAX_UPLOAD_MB` | Maximale Dateigröße |

### Welche KI?

- **Anthropic (Claude):** die beste Erkennung. Die Unterlagen gehen dabei an die API. WEG-Protokolle enthalten Namen und teils Zahlungsrückstände anderer Eigentümer, das solltest du bedenken. Eine typische Prüfung mit 100–200 Seiten kostet grob im Bereich von einigen Cent bis wenigen Euro, je nach Modell.
- **Lokal mit Ollama:** Die Daten bleiben bei dir, es kostet nichts. Dafür ist die Erkennung schwächer und es braucht ordentlich Hardware (für ein 14B-Modell etwa 16 GB RAM, mit GPU deutlich schneller). Ollama kann in einem eigenen LXC auf demselben Proxmox laufen.
- **Ohne KI:** Die Stichwort-Prüfung findet die meisten Warnsignale, erzeugt aber mehr Treffer, die du selbst sortieren musst.

## Sicherheit

Die Anwendung ist für dein Heimnetz gedacht. Stell sie nicht ungeschützt ins Internet. Für Zugriff von unterwegs nutze ein VPN (WireGuard, Tailscale) oder einen Reverse Proxy mit HTTPS und setze `APP_PASSWORD`.

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
- `app/analyze.py`: Verarbeitung im Hintergrund, Zitatprüfung, Zusammenfassung
- `app/main.py`: Web-API und Bericht
- `app/static/`: Oberfläche ohne Framework und ohne Build-Schritt

## Lizenz

MIT
