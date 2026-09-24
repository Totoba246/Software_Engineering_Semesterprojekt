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

### c. Personas

#### 🏢 **Herr Weber (48, Betriebsleiter beim Gerätebetreiber)**

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
| F02 | **Statusregeln & Warnungen**          | Fachlich geprüfte Regeln stufen den Ladezustand ein (z. B. normal / niedrig / kritisch) und lösen bei kritischem Zustand eine Vorwarnung aus | 🟢 Hoch    |
| F03 | **Verlaufsanzeige**                   | Darstellung, wie sich der Batteriezustand eines Geräts über die Zeit entwickelt hat                                                          | 🟠 Mittel  |
| F04 | **Wechselprognose (Prediction)**      | Abschätzung, wann ein Batteriewechsel voraussichtlich nötig wird, auf Basis der Verlaufsdaten                                                | 🟡 Niedrig |
| F05 | **Kategorisierung/Filter der Geräte** | Gruppierung bzw. Filterung der Geräte, z. B. nach Standort oder Gerätetyp                                                                    | 🟠 Mittel  |
| F06 | **Login/Authentifizierung**           | Zugangsschutz für die Anwendung                                                                                                              | 🟢 Hoch    |
| F07 | **Gerätestammdaten**                  | Anlegen/Pflegen von Metadaten je Gerät (Ort, Typ, Zuordnung zum Betreiber) – Voraussetzung für F05                                           | 🟠 Mittel  |
| F08 | **Datenaufnahme ab MQTT**             | Entgegennahme, Validierung und Speicherung der auf dem MQTT-Broker veröffentlichten Messnachrichten (Strom, Spannung, GPS, Zeitstempel)      | 🟢 Hoch    |
| F09 |**Servicetechniker Zuordnung**  | Mitabreiter ordnen Servicetechnikern Geräte zu., diese sehen nur die ihm zugeordneten Geräte | 🟡 Niedrig | 

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

## 🧩 Architektur

> Detaillierte C4-Diagramme, Sequenzdiagramm und ADRs folgen in A04 (Softwarearchitektur & Schnittstellen).

- **Context:** BatteryWatch als Softwaresystem ab MQTT-Broker; TrafficNode-Hardware/Firmware sind vorgelagert und nicht Teil des Systems
- **Container:** Frontend, Backend, Datenbank, MQTT-Broker

- **Code:** tbd – Sprache/Framework für Frontend und Backend sind im Team noch festzulegen

---

## 🧰 Tools & Technologien

- **Versionsverwaltung:** GitHub (mit Issues)
- **Backend:** tbd
- **Frontend:** tbd
- **Datenbank:** tbd
- **MQTT-Broker:** tbd 
- **Coding:** Einsatz eines KI-Coding-Agents (z. B. Claude, Codex)

---