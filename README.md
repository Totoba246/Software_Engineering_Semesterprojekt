# 🔋 BatteryWatch – Fernüberwachung des Batteriezustands mobiler Geräte
---

## 🧭 1. Kontext

### a. Beschreibung

Ein Unternehmen betreibt mobile, batteriebetriebene Geräte ohne eigene digitale Zustandsüberwachung. Schwache oder leere Batterien führen zu Geräteausfällen und ungeplanten Serviceeinsätzen.

**BatteryWatch** ist das Softwaresystem, mit dem der Betreiber den Batteriezustand seiner Geräte zentral und aus der Ferne beobachten sowie dessen Verlauf nachvollziehen kann. Ziel ist es, Batteriewechsel rechtzeitig zu planen und kurzfristige Wechsel und Ausfälle zu vermeiden. Auf lange Sicht sollen die gesammelten Verlaufsdaten außerdem genutzt werden, um geeignete Wechselzeitpunkte abzuschätzen.

Die Geräte sind mit einer nachrüstbaren Telemetriebox (**TrafficNode**) ausgestattet, die Strom, Spannung und GPS-Position erfasst. Hardware und Firmware der TrafficNode werden in diesem Projekt **nicht** entwickelt – sie dienen nur dem Problem- und Datenverständnis. Die eigentliche Softwareaufgabe beginnt am **MQTT-Broker**, auf dem die Messnachrichten der Geräte veröffentlicht werden.

### b. Stakeholder

|Stakeholder|Beschreibung|Ziel / Interesse|
|---|---|---|
|🧑‍💻 **Entwicklungsteam**|Dreierteam aus Studierenden|Umsetzung eines durchgängigen, geprüften Softwaresystems|
|🏢 **Betreiber (Unternehmen)**|Eigentümer und Hauptnutzer der überwachten Geräte|Geräteausfälle vermeiden, Batteriezustand zentral im Blick behalten|
|🔧 **Servicetechniker/innen**|Personal, das mit dem Batteriewechsel beauftragt wird|Planungssicherheit: wissen, wann und wo ein Wechsel ansteht|

###### *Wer wartet die Software, setzt den Server auf, etc.

### c. Nutzerrollen (Login-Rollen)

Beim Betreiber gibt es mehrere eigenständige Personen/Rollen mit eigenem Login:

|Rolle|Rechte|
|---|---|
|👑 **Admin**|Technische Verwaltung: Nutzerkonten anlegen/verwalten, Systemkonfiguration|
|🏢 **Firmenchef**|Volle Geschäftssicht: alle Geräte & Batteriezustände, Servicetechniker zuordnen, Benachrichtigung bei kritischem Akkustand – gleiche Rechte wie Mitarbeiter|
|🧑‍💼 **Mitarbeiter**|Volle Geschäftssicht: alle Geräte & Batteriezustände, Servicetechniker zuordnen, Benachrichtigung bei kritischem Akkustand – gleiche Rechte wie Firmenchef|
|🔧 **Servicetechniker/in**|Sieht nur die ihm/ihr zugeordneten Geräte|

### d. Personas

#### 🏢 **Herr Weber (48, Betriebsleiter/Firmenchef beim Gerätebetreiber)**

- Verantwortet den reibungslosen Einsatz der mobilen Geräte
- Will auf einen Blick sehen, welche Geräte eine schwache Batterie haben
- Möchte frühzeitig gewarnt werden, statt Ausfälle zu spät zu bemerken

#### 🔧 **Frau Aydin (33, Servicetechnikerin)**

- Erhält Aufträge zum Batteriewechsel
- Braucht verlässliche Informationen, _welches_ Gerät _wo_ gewechselt werden muss
- Profitiert von einer Kategorisierung der Geräte nach Standort/Art, um Einsätze zu bündeln
- möchte Aufträge frühzeitig erhalten um besser planen zu können

## ⚙️ 2. Funktionale Anforderungen

| ID  | Anforderung                           | Beschreibung                                                                                                                                 | Priorität  |
| --- | ------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- | ---------- |
| F01 | **Geräteübersicht**                   | Zentrale Liste/Ansicht aller überwachten Geräte mit aktuellem Batterieladezustand                                                            | 🟢 Hoch    |
| F02 | **Statusregeln & Warnungen**          | Fachlich geprüfte Regeln stufen den Ladezustand ein (z. B. normal / niedrig / kritisch) und lösen bei kritischem Zustand eine Vorwarnung aus | 🟠 Mittel  |
| F03 | **Verlaufsanzeige**                   | Darstellung, wie sich der Batteriezustand eines Geräts über die Zeit entwickelt hat                                                          | 🟠 Mittel  |
| F04 | **Wechselprognose (Prediction)**      | Abschätzung, wann ein Batteriewechsel voraussichtlich nötig wird, auf Basis der Verlaufsdaten                                                | 🟡 Niedrig |
| F05 | **Kategorisierung/Filter der Geräte** | Gruppierung, Filterung und Sortierung der Geräte, z. B. nach Standort, Gerätetyp oder Akkustand                                              | 🟠 Mittel  |
| F06 | **Login/Authentifizierung**           | Zugangsschutz für die Anwendung mit den Rollen Admin, Firmenchef, Mitarbeiter und Servicetechniker (siehe 1.c)                               | 🟢 Hoch    |
| F07 | **Gerätestammdaten**                  | Anlegen/Pflegen von Metadaten je Gerät (Ort, Typ, Zuordnung zum Betreiber) – Voraussetzung für F05                                           | 🟠 Mittel  |
| F08 | **Datenaufnahme ab MQTT**             | Entgegennahme, Validierung und Speicherung der auf dem MQTT-Broker veröffentlichten Messnachrichten (Strom, Spannung, GPS, Zeitstempel)      | 🟢 Hoch    |
| F09 | **Servicetechniker Zuordnung**        | Firmenchef/Mitarbeiter ordnen Servicetechnikern Geräte zu, diese sehen nur die ihnen zugeordneten Geräte                                     | 🟡 Niedrig |
| F10 | **Kartenansicht**                     | Darstellung aller TrafficNodes auf einer Karte; Klick auf einen Node führt zur Detailansicht                                                 | 🟡 Niedrig |
| F11 | **Detailansicht**                     | Detailseite je Gerät mit Standort auf Karte, Koordinaten/Ort, aktuellem Akkustand und Akkuverlauf; zusätzlich für Firmenchef/Mitarbeiter der zugeordnete Servicetechniker | 🟠 Mittel  |
| F12 | **Kalender-Ansicht voraussichtlicher Ausfälle** | Darstellung der voraussichtlichen Batterie-Ausfälle (auf Basis von F04) in einer Kalenderansicht; Firmenchef/Mitarbeiter sehen alle Geräte, Servicetechniker nur die ihnen zugeordneten | 🟡 Niedrig |
| F13 | **Privater Kalender für Servicetechniker** | Servicetechniker können sich eigene Termine eintragen, wann sie welche Batterie wechseln wollen                                             | 🟡 Niedrig |

*Beim einrichten eines Geräts einmalig festlegen, welche Kategorie

---

## 🧱 3. Nicht-funktionale Anforderungen

| Kategorie         | Beschreibung                                                                      | Ziel                                              |
| ----------------- | --------------------------------------------------------------------------------- | ------------------------------------------------- |
| **Usability**     | Intuitive, klare Benutzeroberfläche für Geräteübersicht und Warnungen             | Geringe Einarbeitungszeit                         |
| **Performance**   | Kurze Ladezeiten der Geräteübersicht auch bei wachsender Geräteanzahl             | Hohe Reaktionsgeschwindigkeit                     |
| **Sicherheit**    | Sichere Authentifizierung | Datenschutz gewährleisten                         |
| **Verfügbarkeit** | Betriebsfähiges Deployment (Cloud oder lokal)                                     | Durchgehende Verfügbarkeit im Demo-/Übungsbetrieb |
| **Modularität**   | Klare Trennung von Datenaufnahme, Statusregeln, Prognose und Anzeige              | Erweiterbarkeit (z. B. spätere ML-Erweiterung)    |
| **Testbarkeit**   | Unit- und Integrationstests A06                     | Codequalität sicherstellen                        |
| **Wartbarkeit**   | Saubere Code-Struktur, laufend gepflegte Dokumentation                            | Einfache Weiterentwicklung durch das Team         |

###### *Genauer, mit Testbarkeit (Kurze Ladezeiten, < 50ms oder so)
---

## 🧭 4. Abgrenzung & MVP

Das Projekt wird **inkrementell** entwickelt.

### 🎯 MVP (bis A06)

- Datenaufnahme ab MQTT-Broker inkl. Speicherung (F08)
- Aktuelle Geräteübersicht mit Batterieladezustand (F01)
- Login/Authentifizierung (F06)
- Kategorisierung/Filter der Geräte (F05, F07)

### 🚫 nicht Teil des MVP

- Verlaufsanzeige über längere Zeiträume (F03)
- Wechselprognose/Prediction (F04)
- Geprüfte Statusregeln mit Vorwarnung bei kritischem Ladezustand (F02)
- Kartenansicht (F10)
- Detailansicht (F11)
- Kalender-Ansicht voraussichtlicher Ausfälle (F12)
- Privater Kalender für Servicetechniker (F13)

---

## 📖 5. Dictionary / Gemeinsames Begriffsverzeichnis

|Bevorzugter Begriff|Englisch / Code|Definition im Projekt|Abgrenzung / alternative Bezeichnungen|
|---|---|---|---|
|**Gerät**|Device|Ein mobiles, batteriebetriebenes Gerät des Betreibers, das mit einer TrafficNode ausgestattet ist|Nicht die TrafficNode selbst, sondern das Gerät, an dem sie angebracht ist|
|**Telemetriebox (TrafficNode)**|Telemetry unit|Nachrüstbare Hardware, die Strom, Spannung und GPS-Position eines Geräts erfasst und per MQTT veröffentlicht|Wird in diesem Projekt nicht entwickelt, nur genutzt|
|**Batteriezustand**|Battery state|Der aus Strom-/Spannungsmessungen abgeleitete, aktuelle Zustand der Batterie eines Geräts|Nicht gleichzusetzen mit dem reinen Rohmesswert|
|**Statusregel**|Status rule|Fachlich geprüfte Regel, die einen Batteriezustand in eine Kategorie (z. B. normal/niedrig/kritisch) einordnet|Regeln sind zu dokumentieren und zu begründen (siehe A06)|
|**Wechselprognose**|Replacement prediction|Abschätzung, wann ein Batteriewechsel für ein Gerät voraussichtlich nötig wird|Verfahren (Regeln vs. ML) ist noch offen|
|**Betreiber**|Operator|Das Unternehmen, dem die überwachten Geräte gehören|Hauptnutzer im Sinne der Stakeholder-Tabelle|
|**Servicetechniker/in**|Service technician|Person, die mit der Durchführung eines Batteriewechsels beauftragt wird|Nicht automatisch Nutzer/in mit Login|
|**Verlauf**|History|Zeitliche Abfolge gespeicherter Batteriezustände eines Geräts|Grundlage für F03 und F04|
|**MVP**|Minimum Viable Product|Der in Abschnitt 4 vorgeschlagene Funktionsumfang mit dem Kernnutzen|Weitere Anforderungen gehören nicht automatisch dazu|



---

## 🚀 Schnellstart (auf dem eigenen Rechner)

Voraussetzung: [Docker Desktop](https://www.docker.com/products/docker-desktop/) läuft, Python ist installiert.

```bash
python start.py
```

Beim ersten Start wird gefragt: echte Daten von Node 101 (MQTT-Passwort nötig) oder Testdaten.
Danach öffnet sich http://localhost:20800. Weitere Befehle: `python start.py help`.

**Anleitung Schritt für Schritt: [docs/Run-locally.md](docs/Run-locally.md)** ·
**Wie alles zusammenhängt: [docs/How-it-works.md](docs/How-it-works.md)** ·
Später auf dem Kursserver: [docs/Server.md](docs/Server.md) ·
Details (Tests, Import, Entwicklung): [docs/Entwicklung.md](docs/Entwicklung.md) ·
[MQTT-Vertrag](docs/MQTT-Vertrag.md) · [Statusregeln](docs/Statusregeln.md)

---

## ✅ Umsetzungsstand

| ID | Anforderung | Stand |
|---|---|---|
| F01 | Geräteübersicht | ✅ Liste + Karte mit Akkustand, Status, letzter Meldung |
| F02 | Statusregeln & Warnungen | 🟡 Regeln umgesetzt ([Statusregeln](docs/Statusregeln.md)), Warnhinweis in der Webseite; keine E-Mail/Push |
| F03 | Verlaufsanzeige | ✅ 24 Std. / 7 / 30 Tage / gesamt, Akkustand, Spannung, Strom |
| F04 | Wechselprognose | 🟡 einfache Schätzung „voraussichtlich kritisch/leer“ aus dem 72-Std.-Trend |
| F05 | Filter/Sortierung | ✅ Status, Kategorie, Ort, Servicetechniker, Suche, Sortierung |
| F06 | Login/Rollen | ✅ Admin, Firmenchef, Mitarbeiter, Servicetechniker (ADR-09) |
| F07 | Gerätestammdaten | ✅ Geräte anlegen, bearbeiten, löschen; Name, Kategorie, Ort (Position kommt per GPS, Mittel der letzten 3 Tage) |
| F08 | Datenaufnahme MQTT | ✅ Collector + Import der Kurs-Datenbank |
| F09 | Techniker-Zuordnung | ✅ je Gerät ein Servicetechniker; Techniker sieht nur seine Geräte |
| F10 | Kartenansicht | ✅ Karte in der Übersicht und Detailansicht |
| F11 | Detailansicht | ✅ inkl. Stammdaten und zugeordnetem Techniker (nur Firmenchef/Mitarbeiter) |
| F12, F13 | Kalender | ❌ noch offen (niedrige Priorität) |

---

## 🧩 Architektur

> Detaillierte C4-Diagramme, Sequenzdiagramm und ADRs folgen in A04 (Softwarearchitektur & Schnittstellen).

- **Context:** BatteryWatch als Softwaresystem ab MQTT-Broker; TrafficNode-Hardware/Firmware sind vorgelagert und nicht Teil des Systems
- **Container:** Frontend, Backend, Datenbank, MQTT-Broker

- **Code:** Python (FastAPI, paho-mqtt, psycopg) im Backend, React im Frontend – siehe [ADR](docs/ADR.md) und [Entwicklung](docs/Entwicklung.md)

---

## 🧰 Tools & Technologien

- **Versionsverwaltung:** GitHub (mit Issues)
- **Backend:** Python 3.12, FastAPI (REST-API), paho-mqtt (Collector), psycopg 3
- **Frontend:** React 18 + Vite, Recharts (Verlauf), Leaflet/OpenStreetMap (Karte)
- **Datenbank:** PostgreSQL 16
- **MQTT-Broker:** Mosquitto 2 (lokal/Docker); Collector kann auch den Live-Broker des Kurses abonnieren
- **Betrieb:** Docker Compose
- **Coding:** Einsatz eines KI-Coding-Agents (z. B. Claude, Codex)

---