"""Erzeugt fiktive Beispielunterlagen zum Testen (keine echten Daten)."""
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import pymupdf, textwrap

def write_pdf(path, pages):
    c = canvas.Canvas(path, pagesize=A4)
    for lines in pages:
        y = 800
        for ln in lines:
            for part in textwrap.wrap(ln, 95) or [""]:
                c.setFont("Helvetica", 10); c.drawString(50, y, part); y -= 14
        c.showPage()
    c.save()

prot = [[
"Niederschrift über die ordentliche Eigentümerversammlung 2024",
"WEG Musterstraße 12, 76131 Karlsruhe (fiktiv)",
"Datum: 14.05.2024, Beginn 18:00 Uhr, Ort: Gemeindesaal",
"TOP 1: Begrüßung und Feststellung der Beschlussfähigkeit. Die Versammlung ist beschlussfähig.",
"TOP 2: Genehmigung der Jahresabrechnung 2023. Die Abrechnung wurde mehrheitlich genehmigt.",
"TOP 3: Entlastung des Verwalters. Die Entlastung wurde nicht erteilt, da die Abrechnung 2022 verspätet vorgelegt wurde.",
],[
"TOP 4: Dachsanierung. Der Sachverständige Herr Beispiel hat im Gutachten vom 02.02.2024 erhebliche Schäden an der Dacheindeckung festgestellt.",
"Die Kosten werden auf ca. 185.000 € geschätzt. Die Erhaltungsrücklage reicht nicht aus.",
"Beschluss: Zur Finanzierung wird eine Sonderumlage in Höhe von 120.000,00 € beschlossen, fällig in zwei Raten zum 01.09.2024 und 01.03.2025, verteilt nach Miteigentumsanteilen.",
"Abstimmung: 612/1000 Ja, 250/1000 Nein, Rest Enthaltung. Beschluss angenommen.",
"TOP 5: Fassade. Die Fassadensanierung (WDVS) wird erneut vertagt, da Angebote noch nicht vorliegen. Der Verwalter soll weitere Angebote einholen.",
],[
"TOP 6: Feuchtigkeit im Keller. In Kellerraum 3 wurde erneut ein Wasserschaden gemeldet. Die Ursache ist noch unklar.",
"Es besteht Verdacht auf Schimmel. Eine Leckortung wird beauftragt.",
"TOP 7: Hausgeldrückstände. Ein Eigentümer ist mit 8.400 € im Rückstand. Der Verwalter wird ermächtigt, ein Mahnverfahren einzuleiten und einen Rechtsanwalt zu beauftragen.",
"TOP 8: Ein Eigentümer kündigt an, den Beschluss zu TOP 4 im Wege der Anfechtungsklage beim Amtsgericht anzugreifen.",
"TOP 9: Eine Kurzzeitvermietung über Airbnb in Einheit 7 führt zu Beschwerden wegen Lärm.",
"Ende der Versammlung 21:15 Uhr.",
]]
write_pdf("samples/Protokoll_ETV_2024.pdf", prot)

ja = [[
"Jahresabrechnung 2023 mit Vermögensbericht",
"WEG Musterstraße 12 (fiktiv)",
"Gesamtkosten 2023: 96.540,12 €",
"Hausgeld gesamt Soll 2023: 98.400,00 €",
"Vermögensbericht:",
"Erhaltungsrücklage Stand 01.01.2023: 58.200,00 €",
"Zuführung zur Erhaltungsrücklage 2023: 18.000,00 €",
"Entnahme aus der Erhaltungsrücklage für Heizungsreparatur: 11.350,00 €",
"Erhaltungsrücklage Stand 31.12.2023: 64.850,00 €",
"Es ist keine Sonderumlage erforderlich.",
]]
write_pdf("samples/Jahresabrechnung_2023.pdf", ja)

# Scan simulieren: Seiten als Bild ohne Textebene
prot22 = [[
"Protokoll der Eigentümerversammlung vom 20.06.2022",
"WEG Musterstraße 12 (fiktiv)",
"TOP 3: Die Heizungsanlage (Baujahr 1994) ist störanfällig. Ein Heizungstausch nach GEG wird diskutiert.",
"Beschluss: Das Thema wird auf die nächste Versammlung vertagt.",
"TOP 4: Die Dachrinne ist undicht. Der Hausmeister soll dies prüfen.",
]]
write_pdf("samples/_tmp.pdf", prot22)
src = pymupdf.open("samples/_tmp.pdf"); out = pymupdf.open()
for p in src:
    pix = p.get_pixmap(dpi=200)
    np_ = out.new_page(width=p.rect.width, height=p.rect.height)
    np_.insert_image(np_.rect, stream=pix.tobytes("jpeg", jpg_quality=70))
out.save("samples/Protokoll_ETV_2022_Scan.pdf")
import os; os.remove("samples/_tmp.pdf")
print("ok")
