# Prompt: Präsentation „Architektur- und Designentscheidungen“ (Deutsch)

> Diesen gesamten Text in eine neue Claude-Sitzung kopieren und die unten genannten Dateien
> anhängen (oder Claude Zugriff auf den Ordner `d:\siemens\pilot` geben).

---

## Rolle und Ziel

Du bist ein erfahrener SPS-Softwarearchitekt im Sondermaschinenbau. Erstelle eine
**deutschsprachige Foliensammlung (12–15 Folien)**, mit der ich in einem Vorstellungsgespräch
bei der **Jonas & Redmann Automationstechnik GmbH** (Berlin; Sondermaschinenbau, Montage- und
Handhabungsanlagen für Batteriezellen, Solar, Medizintechnik) mein Pilotprojekt vorstelle.
Die Stelle: **SPS-Softwareentwickler**. Die Zuhörer sind Softwareleiter und Entwickler aus der
Automatisierung. Sie bewerten Struktur, Begründungen und Qualitätsbewusstsein – nicht Effekte.

Der Schwerpunkt liegt auf den **Architektur- und Designentscheidungen**: Jede wichtige
Entscheidung wird als **Entscheidung → Begründung → verworfene Alternative** gezeigt.

Vortragsdauer: ca. 12–15 Minuten. Zu jeder Folie gehören **Sprechernotizen auf Deutsch**
(3–6 Sätze, in der Ich-Form, so formuliert, wie ich sie frei sprechen würde).

## Sprache und Terminologie

- Alle Folientexte und Notizen auf **Deutsch**, sachlich, kurz, ohne Marketing-Sprache.
- Fachbegriffe so, wie sie in der deutschen Automatisierung üblich sind:
  Funktionsbaustein (FB), Funktion (FC), Datenbaustein (DB), Organisationsbaustein (OB),
  PLC-Datentyp (UDT), Multiinstanz, Schrittkette, Betriebsartenmanagement,
  Not-Halt, Schutztür / Schutztürverriegelung, Stopp-Kategorie 0/1 (DIN EN 60204-1),
  Performance Level / PLr (DIN EN ISO 13849-1), Diskrepanzüberwachung, zweikanalig,
  Quittierung / Rücksetzen, Wiederanlaufsperre, Inbetriebnahme, Abnahme.
- Englische Begriffe nur, wo sie im Alltag Standard sind (CI/CD, Pull Request, Release,
  Unit-Test, PackML).

## Fakten (nur diese verwenden – nichts erfinden)

**Anlage:** Prüf- und Sortierstation für Batteriezellen. Förderband bringt Zellen zur
Messstation (Leerlaufspannung, Innenwiderstand), Einstufung A / B / Ausschuss, A läuft weiter
zur Modulmontage, B und Ausschuss werden von zwei Pneumatikzylindern in Behälter geschoben.

**Plattform:** SIMATIC S7-1500, CPU 1516-3 PN/DP (Standard-CPU), TIA Portal V20, SCL;
HMI: WinCC Unified PC Runtime V20; PROFINET-Subnetz PN_IE_1 (PLC 192.168.0.1, HMI 192.168.0.2).

**Bausteinstruktur:**
- `OB_CellSorting` (Zyklus-OB) → `FB_CellSortingMain` (Verschaltung, HMI-Spiegelung)
- Multiinstanzen: `FB_SafetyMonitor` (Sicherheitsfunktionen) mit 2× `FB_DualChannel`;
  `FB_ProcessSim` (Anlagensimulation); `FB_SortStation` (Betriebsarten + Schrittkette)
  mit 2× `FB_Cylinder`
- `FC_GradeCell` (Einstufung, zustandslos), `FC_AnyFault` (eine einzige Definition von „Störung“)
- `DB_HMI` (DB1, Schnittstelle zum HMI: Cmd / Par / Sts), 4 UDTs
  (CellData, GradeLimits, Counters, Alarms)

**Designentscheidungen (je eine Folie oder gebündelt):**
1. *Betriebsarten getrennt von der Schrittkette* (PackML-angelehnt: STOPPED → RESETTING →
   IDLE → EXECUTE, jede Störung → ABORTED). Schritte 100, 110 … 140, damit neue Schritte
   dazwischen passen. Alternative verworfen: eine einzige große Schrittkette.
2. *Ausgänge jeden Zyklus zuerst AUS*, der aktive Schritt schaltet ein, was er braucht →
   kein vergessener gesetzter Aktor. Alternative: Setzen/Rücksetzen verteilt im Code.
3. *Fehlerreaktion im selben Zyklus* (Region `Fault_reaction` am Bausteinende): Jede Störung
   erzwingt ABORTED und schaltet alle Aktoren sofort ab.
4. *Wiederverwendbarer `FB_Cylinder`* mit Endlagenüberwachung (2 s) und monostabilem Ventil
   (stromlos = eingefahren = sicher).
5. *Zustandslose `FC_GradeCell`* mit Grenzwerten als Parameter (`DB_HMI.Par`) → neuer
   Zelltyp ohne Codeänderung, isoliert testbar.
6. *Stopp erst am Zyklusende* → nie eine halb sortierte Zelle.
7. *Interner Zustand in statischen Variablen, Ausgänge nur am Ende geschrieben*
   (vorher 26 Compiler-Warnungen „might not be initialized“, danach 0).
8. *HMI-Kommandos als Einmal-Befehle*, von der SPS quittiert; ein einziger Schnittstellen-DB.
9. *Simulation als eigener FB* → Logik ohne Hardware testbar; an der echten Anlage durch das
   E/A-Mapping ersetzt, `FB_SortStation` bleibt unverändert.
10. *Nicht integrierte HMI-Verbindung unter V20* → `DB_HMI` mit Standardzugriff (nicht
    optimiert) und absoluter Adressierung (Offsets nach S7-Ausrichtungsregeln berechnet,
    jede Adresse von TIA zurückgelesen). Begründung: Einschränkung von V20 bei Openness.

**Sicherheit (DIN EN ISO 12100 / 13849-1 / 60204-1 / ISO 13850 / ISO 14119):**
- SF1 Not-Halt: Stopp-Kategorie 0, Energie im selben Zyklus weg, PLr d
- SF2 Schutztür: Stopp-Kategorie 1, kontrolliertes Stillsetzen, Energie nach 1 s weg, PLr d
- SF3 Rücksetzen: nur bei *Loslassen* des Tasters (fallende Flanke), Taster > 5 s gedrückt
  = klemmt → ignoriert; kein automatischer Wiederanlauf, auch nicht nach Netzwiederkehr
- Zweikanalig mit Diskrepanzüberwachung 500 ms (Kategorie 3); Fehler erst quittierbar,
  nachdem beide Kanäle gleichzeitig offen waren
- Risikograph: SF1 S2/F1/P2 → d; SF2 S2/F2/P1 → d
- **Ehrlich darstellen:** In diesem Pilot läuft das als *Spiegel in der Standard-SPS*
  (`FB_SafetyMonitor`). An der echten Anlage gehört es in eine F-CPU mit STEP 7 Safety
  (ESTOP1, SFDOOR, FDBACK, ACK_GL) und PROFIsafe-F-Peripherie. Validierung an der Maschine
  (DIN EN ISO 13849-2) und SISTEMA-Berechnung sind offene Punkte.

**Qualitätssicherung:**
- Kein PLCSIM in der Lizenz → eigene **SCL-Testlaufzeit** in Python, die *dieselben*
  `.scl`-Dateien ausführt, die in TIA importiert werden (zyklusbasiert, simulierte Zeit).
- **84 Unit-Tests**, systematisch entworfen: Grenzwertanalyse, Äquivalenzklassen,
  Entscheidungstabellen, Zustandsübergänge, Use Cases, Glass-Box.
- **SCL-Entscheidungsüberdeckung 99,1 %** (114 von 115; der Rest ist nachweislich
  unerreichbarer Defensivcode).
- **3 echte Fehler durch die Tests gefunden und behoben:**
  1. Zelle mit R = 0 oder negativem Innenwiderstand (Kurzschluss!) wurde als **A** eingestuft
     → Plausibilitätsprüfung ergänzt
  2. Zylinderventil fiel erst **einen Zyklus nach** dem Fehler ab
  3. Störungen schalteten erst **einen Zyklus zu spät** nach ABORTED
- TIA: **0 Fehler, 0 Warnungen**.

**Versionierung und CI/CD:**
- Jeder Baustein hat `VERSION`; Manifest `src/block_versions.json` mit Fingerabdruck von
  Schnittstelle und Code. Regel: Schnittstelle geändert → Hauptversion; nur Code geändert →
  Nebenversion; Kommentare ignoriert. Aktuell: 15 Bausteine, alle v1.0.
- GitHub Actions: CI bei jedem Push (ASCII-Prüfung der Quellen, Versionsregeln, Tests,
  Überdeckungsschwelle 95 %, UML-Klassendiagramm wird aus dem Code erzeugt und auf
  Aktualität geprüft). CD bei Versions-Tag: Tests → Release-Paket → optional Import und
  Übersetzen in TIA über Openness auf einem Windows-Runner (vorbereitet, noch nicht aktiv).

## Diagramme (als Bilder einbinden)

| Datei | Inhalt | passende Folie |
|---|---|---|
| `docs/uml/rendered/scl_class_diagram.png` | Bausteinstruktur (aus dem Code generiert) | Architekturüberblick |
| `docs/uml/rendered/state_station.png` | Betriebsarten + Schrittkette | Ablaufsteuerung |
| `docs/uml/rendered/state_safety.png` | Zustände der Sicherheitsfunktionen | Sicherheit |
| `docs/uml/rendered/sequence_estop.png` | Ablauf Not-Halt und Wiederanlauf | Sicherheit |
| `docs/uml/rendered/deployment.png` | SPS, HMI, Netzwerk, CI/CD | Systemüberblick |
| `docs/uml/rendered/activity_cicd.png` | Pipeline mit Prüfschritten | CI/CD |

Die Diagramme sind englisch beschriftet. Auf der Folie den deutschen Titel und eine
deutsche Kernaussage daneben setzen; die Diagramme nicht neu zeichnen.

## Vorgeschlagene Gliederung

1. Titel: „Prüf- und Sortierstation für Batteriezellen – Architektur und Designentscheidungen“
2. Aufgabe und Anlage (Prozess in einem Satz, Bezug zu Batteriezellmontage bei J&R)
3. Systemüberblick (Deployment-Diagramm)
4. Bausteinarchitektur (Klassendiagramm; Schichten: OB → Haupt-FB → Fach-FBs → FCs/UDTs)
5. Ablaufsteuerung: Betriebsarten und Schrittkette (Zustandsdiagramm)
6. Designentscheidungen I – Robustheit (Ausgänge AUS, Fehlerreaktion im selben Zyklus, Stopp am Zyklusende)
7. Designentscheidungen II – Wiederverwendung und Wartbarkeit (FB_Cylinder, FC_GradeCell, Parameter, Schnittstellen-DB)
8. Sicherheitskonzept (SF1–SF3, Stopp-Kategorien, PLr; Zustands- und Sequenzdiagramm)
9. Abgrenzung Standard-SPS ↔ F-CPU (ehrliche Folie: was ist Spiegel, was gehört in die F-CPU)
10. Test ohne Hardware: SCL-Testlaufzeit und Testentwurfsmethoden
11. Ergebnis der Tests: 84 Tests, 99,1 %, 3 gefundene Fehler (stärkste Folie – konkret zeigen)
12. Versionierung der Bausteine (Regeln, Manifest)
13. CI/CD-Pipeline (Aktivitätsdiagramm)
14. Offene Punkte und nächste Schritte (F-CPU, SISTEMA, Validierung, echte E/A, PLCSIM-Test)
15. Zusammenfassung: drei Kernaussagen

## Gestaltung

- Sachlich-technischer Stil, viel Weißraum, eine Kernaussage pro Folie als Folientitel
  (ganzer Satz, z. B. „Jede Störung schaltet alle Aktoren im selben Zyklus ab“).
- Höchstens 5 Stichpunkte pro Folie, höchstens ~12 Wörter pro Stichpunkt.
- Entscheidungsfolien einheitlich als drei Spalten: **Entscheidung | Begründung | Verworfen**.
- Codebeispiele nur kurz (max. 8 Zeilen SCL), z. B. die Region `Fault_reaction` oder die
  Rücksetzlogik mit fallender Flanke.
- Keine erfundenen Zahlen, Kunden, Logos oder Zitate. Kein Firmenlogo von J&R verwenden.

## Ausgabe

- Erzeuge die Präsentation als **PowerPoint (.pptx)** – oder, falls verfügbar, als
  Slides-Artefakt, das als .pptx/PDF exportiert werden kann.
- Danach eine kurze Liste: welche Folie welche Fakten und Diagramme nutzt, und welche
  Aussagen ich im Gespräch besonders sicher beherrschen sollte (mögliche Rückfragen der
  Zuhörer mit einer knappen Antwort auf Deutsch).

## Anzuhängende Dateien

- `docs/uml/rendered/*.png` (6 Diagramme)
- `docs/CellSortingStation_DesignSheet.pdf`, `docs/CellSortingStation_SafetyConcept.pdf`
- `src/02_Blocks.scl` (für kurze Codeausschnitte), `src/block_versions.json`
- optional `tests/test_fb_safety.py`, `tests/test_fc_gradecell.py` (Testentwurfstabellen im Kopf)
