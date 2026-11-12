# Architecture Design Records (ADR) – BatteryWatch

Format je Entscheidung: **Kontext → Entscheidung → Konsequenzen**.

**Rahmenbedingungen:** 3er-Team, begrenzte Projektlaufzeit, wenige Nutzer beim Betreiber, keine Skalierungsanforderung. Datenquelle sind MQTT-Nachrichten der TrafficNodes.

| ADR | Thema | Status |
| --- | --- | --- |
| 01 | Modularer Monolith | ✅ akzeptiert |
| 02 | Python als Backend-Sprache | ✅ akzeptiert |
| 03 | Prognose als separater Service | ✅ akzeptiert |
| 04 | Eine gemeinsame PostgreSQL-Datenbank | ✅ akzeptiert |
| 05 | Eigener MQTT-Broker für Telemetrie | ✅ akzeptiert |
| 06 | REST-API mit Polling (5 min) | ✅ akzeptiert |
| 07 | React als Frontend | ✅ akzeptiert |
| 08 | Docker für Entwicklung und Bereitstellung | ✅ akzeptiert |
| 09 | Login und Autorisierung in Eigenimplementierung | ✅ akzeptiert |
| 10 | Collection-Service für die Datenaufnahme | ✅ akzeptiert |
| 11 | Bibliotheken für Backend und Frontend | ✅ akzeptiert |

---

## ADR-01 · Modularer Monolith als Grundarchitektur

- **Kontext:** Kleines Team, geringe Last. Microservices würden Betriebs- und Abstimmungsaufwand erzeugen, ohne Nutzen zu bringen. Gleichzeitig fordert die NFA *Modularität* eine klare Trennung von Datenaufnahme, Statusregeln, Prognose und Anzeige.
- **Entscheidung:** Das Backend wird als **ein** Deployable umgesetzt, intern in fachliche Module gegliedert (Statusregeln, Geräteverwaltung, Auth, API). Datenaufnahme (ADR-10) und Prognose (ADR-03) laufen bewusst als eigene Services.
- **Konsequenzen:**
  - ➕ Einfache Entwicklung, Tests und Deployment
  - ➕ Module kommunizieren per direktem Funktionsaufruf – keine Netzwerklatenz, keine verteilten Fehler
  - ➖ Module skalieren nicht unabhängig (bewusst akzeptiert)

## ADR-02 · Python als Backend-Sprache

- **Kontext:** Das Team hat die meiste Erfahrung mit Python. Die spätere ML-Erweiterung (Teil B) ist in Python ebenfalls am besten unterstützt.
- **Entscheidung:** Monolith, Collection-Service und Prediction-Service werden in **Python** entwickelt. Das Web-Framework wird bei Projektstart festgelegt.
- **Konsequenzen:**
  - ➕ Schneller Einstieg, ein einheitlicher Stack für alle Backend-Teile
  - ➕ Reife Bibliotheken für MQTT, PostgreSQL und ML

## ADR-03 · Prognose als separater Service (nicht im MVP)

- **Kontext:** Die Wechselprognose (F04) ist fachlich eigenständig, niedrig priorisiert und wird erst in Teil B umgesetzt.
- **Entscheidung:** Der Prediction-Service wird zur **besseren Übersichtlichkeit** als eigenständiger Service umgesetzt und per **REST** vom Monolithen angesprochen.
- **Konsequenzen:**
  - ➕ Prognoselogik klar vom Kernsystem getrennt, eigene, überschaubare Codebasis
  - ➕ MVP bleibt davon unberührt
  - ➖ Zusätzlicher Container, Schnittstelle muss dokumentiert und getestet werden

## ADR-04 · Eine gemeinsame PostgreSQL-Datenbank

- **Kontext:** Benötigt werden relationale Stammdaten (Geräte, Nutzer, Rollen, Zuordnungen) und zeitbasierte Messwerte (Verlauf, Prognose).
- **Entscheidung:** Monolith, Collection-Service und Prediction-Service greifen auf **eine gemeinsame PostgreSQL**-Datenbank zu.
- **Konsequenzen:**
  - ➕ Nur ein Datenbanksystem zu betreiben, sichern und wiederherzustellen
  - ➕ Zeitreihen sind für die erwartete Datenmenge mit Index auf `(device_id, timestamp)` ausreichend performant
  - ➖ Alle Services hängen vom selben Schema ab → Schemaänderungen immer für alle prüfen

## ADR-05 · Eigener MQTT-Broker für die Telemetrie

- **Kontext:** Die TrafficNodes veröffentlichen ihre Messdaten per MQTT. Für Entwicklung, Tests und Betrieb wird ein kontrollierbarer Broker benötigt.
- **Entscheidung:** Wir betreiben einen **eigenen MQTT-Broker** (z. B. Mosquitto) als Container. Abonniert werden die Telemetrie-Topics vom Collection-Service (ADR-10).
- **Konsequenzen:**
  - ➕ Unabhängig von externer Infrastruktur, lokal und in Tests mit Testpublisher nutzbar
  - ➖ Broker muss selbst konfiguriert und abgesichert werden
  - ⚠️ Payload-Format wird als **MQTT-Vertrag** festgehalten und gegen Abweichungen validiert

## ADR-06 · REST-API mit Polling alle 5 Minuten

- **Kontext:** Frontend und Backend laufen getrennt. Batteriezustände ändern sich langsam, Echtzeit-Updates sind nicht nötig.
- **Entscheidung:** Kommunikation über eine **REST/JSON-API**. Das Frontend aktualisiert die Daten per **Polling alle 5 Minuten**. Innerhalb des Monolithen wird kein REST verwendet (siehe ADR-01).
- **Konsequenzen:**
  - ➕ Einfach, gut testbar, kein WebSocket-Aufwand
  - ➖ Anzeige kann bis zu 5 Minuten veraltet sein (fachlich akzeptabel)

## ADR-07 · React als Frontend

- **Kontext:** Benötigt wird eine interaktive Web-Oberfläche (Übersicht, Filter, Karte, Verlauf, Kalender).
- **Entscheidung:** Single-Page-App mit **React**.
- **Konsequenzen:**
  - ➕ Großes Ökosystem (Karten, Charts, Kalender-Komponenten)
  - ➖ Separater Build und eigener Container

## ADR-08 · Docker für Entwicklung und Bereitstellung

- **Kontext:** Reproduzierbare Umgebung im Team sowie reproduzierbare Lieferung (A07–A09, B09) sind gefordert.
- **Entscheidung:** Alle Komponenten (Backend, Collection-Service, Frontend, PostgreSQL, MQTT-Broker, später Prediction-Service) laufen als **Docker-Container**, orchestriert über **Docker Compose**.
- **Konsequenzen:**
  - ➕ Identische Umgebung lokal, in CI und im Deployment

## ADR-09 · Login und Autorisierung in Eigenimplementierung

- **Kontext:** F06 (Login mit den Rollen Admin, Firmenchef, Mitarbeiter, Servicetechniker) ist Teil des MVP. Externe Identity-Provider (z. B. Keycloak) wären für wenige Nutzer überdimensioniert.
- **Entscheidung:** Login und Rollenprüfung werden **selbst im Auth-Modul des Monolithen** umgesetzt. Passwörter werden mit einem etablierten Verfahren aus einer Bibliothek gehasht (z. B. bcrypt oder Argon2). Die Rechte werden bei jedem API-Endpunkt im Backend geprüft, nicht nur im Frontend.
- **Konsequenzen:**
  - ➕ Keine zusätzliche Infrastruktur, volle Kontrolle über das Rollenmodell
  - ➖ Sicherheitsverantwortung liegt beim Team → Auth gezielt testen (falsches Passwort, fremde Geräte, fehlende Rechte)
  - ⚠️ Session-Cookie vs. Token (JWT) wird bei der Umsetzung von F06 festgelegt

## ADR-10 · Collection-Service für die Datenaufnahme

- **Kontext:** Telemetrie muss dauerhaft vom MQTT-Broker empfangen und gespeichert werden (F08), unabhängig davon, ob gerade jemand die Web-Oberfläche nutzt. Eine MQTT-Dauerverbindung im selben Prozess wie die REST-API vermischt zwei unterschiedliche Aufgaben.
- **Entscheidung:** Ein eigener **Collection-Service** (Python, eigener Container) abonniert die Telemetrie-Topics, validiert die Nachrichten gegen den MQTT-Vertrag und schreibt sie direkt in die gemeinsame Datenbank (ADR-04). Er stellt keine eigene API bereit.
- **Konsequenzen:**
  - ➕ Messwerte werden auch gespeichert, wenn das Web-Backend ausfällt oder neu deployt wird
  - ➕ Klar abgegrenzter, einzeln testbarer Datenpfad (passt zu A05: Testpublisher → Broker → Speicherung)
  - ➖ Ein weiterer Container, der betrieben und überwacht werden muss
  - ⚠️ Ungültige Nachrichten werden verworfen und geloggt, nicht gespeichert

## ADR-11 · Bibliotheken für Backend und Frontend

- **Kontext:** ADR-02 und ADR-07 legen Sprache bzw. Framework fest, nicht aber die konkreten Bibliotheken. Collector, API und Tools sollen Code (MQTT-Vertrag, Statusregeln, DB-Zugriff) teilen.
- **Entscheidung:**
  - **FastAPI** für die REST-API (automatische OpenAPI-Doku unter `/docs`, Validierung mit Pydantic), **paho-mqtt** für den Collector, **psycopg 3** mit reinem SQL statt ORM.
  - Ein gemeinsames Python-Paket `batterywatch` und **ein** Docker-Image; Collector und API laufen trotzdem als getrennte Container (ADR-10), nur mit anderem Startbefehl.
  - Frontend mit **Vite**, **Recharts** für den Verlauf und **Leaflet** mit OpenStreetMap-Kacheln für die Karte.
- **Konsequenzen:**
  - ➕ MQTT-Vertrag und Statusregeln existieren nur einmal und werden von Collector, API und Testpublisher gemeinsam genutzt
  - ➕ SQL bleibt sichtbar und für alle nachvollziehbar (z. B. Glättung, Zeitintervalle des Verlaufs)
  - ➖ Schemaänderungen ohne Migrationswerkzeug; `schema.sql` ist idempotent, spätere Änderungen brauchen ein Migrationskonzept (B05)
  - ➖ Kartenkacheln kommen von openstreetmap.org (Internetzugang im Browser nötig, Nutzungsbedingungen beachten)
