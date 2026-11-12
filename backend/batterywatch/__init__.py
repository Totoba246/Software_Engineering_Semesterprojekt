"""BatteryWatch backend: everything written in Python.

MAP OF THIS FOLDER (backend/batterywatch/)

    config.py        all settings (read from .env via environment variables)
    contract.py      what a valid node message looks like (topic + JSON)
    battery.py       the maths: mV -> corrected voltage -> % -> red/yellow/green
    schema.sql       the database tables
    db.py            writing into the database

    collector/       PROGRAM 1: MQTT broker -> check -> database   (container "collector")
    api/             PROGRAM 2: database -> JSON for the web page   (container "api", port 8000)
    tools/           helpers for testing and importing data (run by hand)

The big picture (all parts, ports, servers) is explained in docs/How-it-works.md.
"""
