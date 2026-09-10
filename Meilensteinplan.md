# Meilensteinplan

Die Meilensteine beziehen sich auf die neue Teil_A-/Teil_B-Struktur. Sie bündeln Zwischenstände; die weiteren Einheiten erzeugen die in ihren Lehrentwürfen beschriebenen Arbeitsprodukte.

| Meilenstein | Termin | Ergebnisstand | Nachweise | Feedback |
|---|---|---|---|---|
| A-M0 | [[Software Engineering I/01 Vorlesung/Teil_A/01 Software-Engineering-Grundlagen & Teamarbeit/A01 - Software-Engineering-Grundlagen & Teamarbeit\|A01]] | Problem und Zusammenarbeit | Problembeschreibung, Teamvereinbarung, eigenes Repository und dokumentarischer PR | Setup-/Problemreview |
| A-M1 | [[Software Engineering I/01 Vorlesung/Teil_A/02 Requirements Engineering & Projektplanung/A02 - Requirements Engineering & Projektplanung\|A02]] | Anforderungen beschrieben | Scope, priorisierte Requirements und Akzeptanzkriterien | Anforderungsreview |
| A-M2 | [[Software Engineering I/01 Vorlesung/Teil_A/03 Domänenanalyse & Modellierung/A03 - Domänenanalyse & Modellierung\|A03]] | Domäne modelliert | Glossar, Domänenmodell, Zustandsregeln und MQTT-Vertragsentwurf | Modellvergleich |
| A-M3 | [[Software Engineering I/01 Vorlesung/Teil_A/04 Softwarearchitektur & Schnittstellen/A04 - Softwarearchitektur & Schnittstellen\|A04]] | Entwicklungsauftrag geprüft | C4, Sequenzdiagramm, ADR, gemeinsamer MQTT-Vertrag und Prüfszenarien | Entwurfsreview vor Implementierung |
| A-M4 | [[Software Engineering I/01 Vorlesung/Teil_A/05 Implementierung, KI-Unterstützung & Clean Code/A05 - Implementierung, KI-Unterstützung & Clean Code\|A05]] | Datenpfad ausführbar | Eigener Testpublisher, lokaler Broker, Speicherung/Abfrage, Tests und reviewed PR | Implementierungsreview |
| A-M5 | [[Software Engineering I/01 Vorlesung/Teil_A/06 Testen & Qualitätssicherung/A06 - Testen & Qualitätssicherung\|A06]] | Kerninkrement geprüft | Anzeige, Statusregeln und risikobasierte Testmatrix | Qualitätsreview |
| A-M6 | [[Software Engineering I/01 Vorlesung/Teil_A/09 Betriebsreife & Datensammlung/A09 - Betriebsreife & Datensammlung\|A09]] | Betriebsreifer Kandidat | CI, Release, Deployment, Runbook, Restore und Datenbefund | Betriebsprüfung |
| A-M7 | [[Software Engineering I/01 Vorlesung/Teil_A/10 Release-Review & Übergabe/A10 - Release-Review & Übergabe\|A10]] | Semesterrelease | Abnahme, Übergabe, Pausenverantwortung und Rückfalllösung | Release-Review |
| B-M1 | [[Software Engineering I/01 Vorlesung/Teil_B/01 Bestandsaufnahme und Softwarewartung/B01 - Bestandsaufnahme und Softwarewartung\|B01]] | Bestand verstanden | System-/Datenaudit und priorisiertes Änderungsbacklog | Auditreview |
| B-M2 | [[Software Engineering I/01 Vorlesung/Teil_B/02 Regression, Refactoring und Reengineering/B02 - Regression, Refactoring und Reengineering\|B02]] | Bestand verbessert | Regression und begründeter Refactoring-PR | Änderungsreview |
| B-M3 | [[Software Engineering I/01 Vorlesung/Teil_B/04 Nutzerfeedback und kontrollierte Systemerweiterung/B04 - Nutzerfeedback und kontrollierte Systemerweiterung\|B04]] | Nutzerbezogene Erweiterung | Änderungsplan aus B03, Nutzerbefund, geprüftes Inkrement und angepasste Verträge | Nutzungs-/Änderungsreview |
| B-M4 | [[Software Engineering I/01 Vorlesung/Teil_B/05 Deployment-Evolution und kontrollierte Migration/B05 - Deployment-Evolution und kontrollierte Migration\|B05]] | Kontrolliertes Update | Deployment-/Migrationsentscheidung und Recovery-Nachweis | Betriebsreview |
| B-M5 | [[Software Engineering I/01 Vorlesung/Teil_B/07 Reproduzierbare ML-Experimente/B07 - Reproduzierbare ML-Experimente\|B07]] | Reproduzierbarer Modellkandidat | Problem, Datenprüfung, Baseline, Experimentvergleich und Model Card | Unabhängige Reproduktion |
| B-M6 | [[Software Engineering I/01 Vorlesung/Teil_B/08 ML-Integration und Betrieb/B08 - ML-Integration und Betrieb\|B08]] | Integrierte ML-Funktion | Modellversion, Vertrag, Integration, Fallback und Monitoring | Integrationsreview |
| B-M7 | [[Software Engineering I/01 Vorlesung/Teil_B/09 Integrationspuffer und unabhängige Reproduktion/B09 - Integrationspuffer und unabhängige Reproduktion\|B09]] | Übernahmefähig | Unabhängiger Systemstart, bearbeitete Befunde und Prozessauswertung | Cross-Team-Review |
| B-M8 | [[Software Engineering I/01 Vorlesung/Teil_B/10 Abschlussdemo und Engineering-Reflexion/B10 - Abschlussdemo und Engineering-Reflexion\|B10]] | Jahresabschluss | Abschlussrelease, Änderungsnachweis, individuelle Erklärungen und Reflexion | Demo und Fachfragen |

## Regeln

- Requirements, Modelle und Dokumentation werden mit dem System weiterentwickelt.
- Reviews und Dokumentation beginnen ab A01. Prüfszenarien entstehen vor der Implementierung; Tests und eine kleine CI ab A05, Vertiefung in A06/A07.
- A03 liefert fachliche Modelle; A04 einen geprüften Entwurf. Erst ab A05 wird der Datenpfad ohne Starter implementiert. Reviewbefunde werden vor dem betroffenen Implementierungsauftrag bearbeitet.
- A10 übergibt einen abgenommenen Stand für die Pause. Reale Pipelineauswahl und studentischer Leistungsnachweis sind getrennte Fragen.
- Der Prozessversuch wird in B03 vereinbart und in B09 bewertet.
- Eine ML-Demonstration ist kein automatischer Nachweis der Eignung für reale Prognosen; Grenzen und Freigabeentscheidung bleiben sichtbar.
- Das Übungsprojekt zählt 20 % der Gesamtnote. Meilensteine dienen Feedback und Überarbeitung; Kriteriengewichte und individuelle Anteile sind separat zu konkretisieren. Das selbst gewählte Abschlussprojekt folgt nach Teil_B.
