from app import rules
from app.analyze import build_chunks, detect_type, verify_quote, _norm


def titles(text):
    return {h["title"] for h in rules.scan_page(text)}


def test_sonderumlage_mit_betrag():
    hits = rules.scan_page("Beschluss: Es wird eine Sonderumlage in Höhe von 120.000,00 € beschlossen.")
    su = [h for h in hits if h["rule_id"] == "su"][0]
    assert su["severity"] == "hoch"
    assert su["amount_eur"] == 120000.0


def test_verneinte_sonderumlage_ist_info():
    hits = rules.scan_page("Es ist keine Sonderumlage erforderlich.")
    assert hits[0]["severity"] == "info" and hits[0]["title"].endswith("(verneint)")


def test_keine_falschtreffer_in_zusammensetzungen():
    t = titles("Die Voraussetzung ist erfüllt. Er hat das ausgerichtet und nichts bestreiten wollen.")
    assert "Risse / Setzungen / Statik" not in t
    assert "Klage / Gericht" not in t
    assert "Streit / Beschwerden" not in t


def test_betraege():
    assert rules.amounts_in("Kosten ca. 185.000 € und EUR 1.250,50") == [185000.0, 1250.5]
    assert rules.amounts_in("rund 1,2 Mio. €") == [1200000.0]


def test_kennzahlen_ruecklage():
    figs = rules.scan_figures("Erhaltungsrücklage Stand 31.12.2023: 64.850,00 €\nZuführung zur Erhaltungsrücklage 2023: 18.000,00 €")
    kinds = {(f["kind"], f["value_eur"]) for f in figs}
    assert ("ruecklage_stand", 64850.0) in kinds
    assert ("ruecklage_zufuehrung", 18000.0) in kinds


def test_dokumenttyp():
    assert detect_type("Niederschrift über die Eigentümerversammlung 2024") == ("protokoll", 2024)
    assert detect_type("Wirtschaftsplan 2025 für die WEG")[0] == "wirtschaftsplan"


def test_zitatpruefung_korrigiert_seite_und_erkennt_erfindung():
    pages = {1: _norm("Begrüßung"), 2: _norm("Die Fassadensanierung wird erneut vertagt, da Angebote fehlen.")}
    assert verify_quote("Die Fassadensanierung wird erneut vertagt", 1, pages) == (2, True)
    assert verify_quote("Der Verwalter ist geflohen und hat das Geld", 2, pages)[1] is False


def test_chunks():
    rows = [{"page_no": i, "text": "x" * 500} for i in range(1, 11)]
    chunks = build_chunks(rows, 1200)
    assert len(chunks) == 5 and "=== Seite 1 ===" in chunks[0]
