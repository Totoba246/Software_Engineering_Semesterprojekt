# Aufgabenstellung

## Ausgangssituation

Ein Unternehmen betreibt mobile, batteriebetriebene Geräte ohne eigene digitale Zustandsüberwachung. Schwache oder leere Batterien können zu Geräteausfällen und ungeplanten Serviceeinsätzen führen.

Das Unternehmen möchte den Batteriezustand aus der Ferne beobachten und dessen Verlauf nachvollziehen können. Damit sollen Batteriewechsel rechtzeitig geplant und unnötige Wechsel vermieden werden. Später sollen die gesammelten Daten darauf untersucht werden, ob sich geeignete Wechselzeitpunkte abschätzen lassen.

Eine nachrüstbare Telemetriebox (TrafficNode) erfasst Strom, Spannung und GPS-Position. Ihre Hardwarebeschreibung dient dem Problem- und Datenverständnis. Die Softwareaufgabe beginnt am MQTT-Broker, auf dem Messnachrichten veröffentlicht werden. Hardware und Firmware werden im Übungsprojekt nicht entwickelt.

## Ziel

Entwickeln Sie im Team ein Softwaresystem, mit dem der Betreiber seine Geräte zentral überwachen kann. Die konkrete Lösung ist zunächst bewusst nicht vollständig spezifiziert. Stakeholder, Nutzungsszenarien, Qualitätsanforderungen und fachliche Statusregeln müssen im Projekt erarbeitet und begründet werden.

Die Implementierung darf in erheblichem Umfang durch Codex oder einen vergleichbaren freigegebenen Coding Agent erfolgen. Das Team bleibt für Problemverständnis, Spezifikation, Architektur, Prüfung, Integration, Betrieb und Qualität verantwortlich.

## Verlauf über Teil_A und Teil_B

**Teil_A:** A01 beginnt mit Fallbeschreibung, Dreierteam und leerem Repository. A02-A04 sind für Anforderungen, fachliche Modelle, Architektur und Schnittstellen reserviert. Ein Entwurfsreview schließt mit einem überprüfbaren Entwicklungsauftrag. Ab A05 implementieren die Teams ohne bereitgestellten Starter einen eigenen Testpublisher und den Datenpfad ab MQTT. A06 ergänzt geprüfte Statusregeln und eine einfache Anzeige. A07-A09 führen zu reproduzierbarer Lieferung und Betriebsreife, A10 dient Release-Review und Übergabe.

**Teil_B:** Das eigene System wird auditiert, kontrolliert verbessert und erweitert. Änderungsplanung, Nutzerfeedback und kontrollierte Updates gehen der begrenzten ML-Erweiterung voraus. B09 dient unabhängiger Reproduktion, B10 dem Abschluss des begleiteten Übungsprojekts.

**Danach:** Eigenes Abschlussprojekt mit selbst gewähltem Thema, vollständiger Umsetzung und einer dem Umfang angemessenen vollständigen Dokumentation. Thema, Abgabe, genauer Dokumentationssatz und Bewertungsdetails werden separat festgelegt.

Das begleitete Übungsprojekt über A/B wird in Dreierteams bearbeitet und zählt 20 % der Gesamtnote. Es dient dem praktischen Anwenden der Theorie und dem Vergleich eigener Lösungen.