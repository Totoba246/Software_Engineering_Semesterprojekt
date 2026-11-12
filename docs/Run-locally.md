# Run BatteryWatch on your own computer

No server, no SSH, no Linux. Everything runs on your laptop.
(Moving it to the course server later is described in [Server.md](Server.md).)

## Once: install Docker Desktop

1. Download and install **Docker Desktop**: https://www.docker.com/products/docker-desktop/
   (Windows: accept the WSL 2 suggestion if it asks; restart the computer if it asks.)
2. Start Docker Desktop. Wait until the whale icon in the taskbar stops moving.

Why Docker? BatteryWatch consists of 5 programs (database, MQTT broker, collector,
API, web server). Docker downloads and runs all of them for you, so you don't
have to install PostgreSQL & co. one by one.

## Start

Open the project folder in VS Code, open a terminal (menu *Terminal → New Terminal*) and type:

```bash
python start.py
```

The very first time it asks:

```
Echte Daten empfangen? (J/n):
```

- **j** (Enter) → you receive the **real node 101**. It then asks for the MQTT password
  (from `tinf25d-llv.yaml`, line `mqtt: passwort:`). Typing is invisible – that's normal.
- **n** → 8 **fake nodes** (SIM-001 … SIM-008) with 30 days of made-up history.
  Works without any password; good for trying things out.

Then it asks for the name and password of the **first admin** (the person who
manages accounts). In test mode it also offers **demo accounts**.

The first start takes a few minutes (downloads + builds). Then your browser opens
**http://localhost:20800** – that's BatteryWatch.

## Login and roles

| Role | Sees / may | Demo account (test mode) |
|---|---|---|
| **Admin** | only the user management: create accounts, change roles, lock, reset passwords, delete | your own admin from the first start |
| **Firmenchef** / **Mitarbeiter** | all devices; add, edit, delete devices; assign service technicians | `chef` / `mitarbeiter` |
| **Servicetechniker** | only the devices assigned to them | `techniker1`, `techniker2` |

Demo password: `demo1234` (only for trying out locally – never on the server).

- **New account:** Admin → *Nutzer anlegen*. The page shows a **start password** once; pass it on.
  At the first login the person must choose their own password.
- **Forgot password:** the admin clicks *Passwort zurücksetzen* – or, if the admin itself forgot it:
  `python start.py reset-password admin`
- **Add a node:** as Firmenchef/Mitarbeiter → *+ Gerät hinzufügen*. The device ID must be the one in
  the node's MQTT topic (`traffic-nodes/101/measurements` → `101`). Nodes that just start sending are
  added automatically anyway; you can then give them a name, place, category and technician on their
  detail page (*Stammdaten → Bearbeiten*). The position on the map always comes from the node's GPS
  (average of the last 3 days); a node without GPS (like node 101 right now) has no position.

## Everyday commands

| Command | What it does |
|---|---|
| `python start.py` | start everything (again) and open the web page |
| `python start.py stop` | stop everything – your data is kept |
| `python start.py status` | show what's running and which mode |
| `python start.py logs` | watch incoming messages live (Ctrl+C to stop watching) |
| `python start.py mode real` | switch to the real node 101 (asks for the MQTT password) |
| `python start.py mode test` | switch to the 8 fake nodes |
| `python start.py demo` | demo accounts + names/places/technicians for the fake nodes |
| `python start.py replay-history` | play the course history back, one message per minute (device `101-sim`) |
| `python start.py reset-password NAME` | set a new password for an account |
| `python start.py reset` | ⚠️ delete ALL local data and start from zero |
| `python start.py help` | list of commands |

Node 101 only sends **every 15 minutes**, so after starting in real mode it can take
up to 15 minutes until it shows up. `python start.py logs` shows when a message arrives.
Right now node 101 sends a broken voltage value (`5368709120`); the web page then
shows the device with a red note explaining why the value was rejected.

## The course history database (old measurements)

Once beforehand (installs our Python libraries, so the check runs with your own Python):

```bash
python -m pip install -r backend/requirements-dev.txt
```

```bash
python start.py check-history      # report: which data is plausible, from when on not?
python start.py import-history     # copy it into your local database
python start.py import-history --to 2026-03-29T00:16:57+00:00   # only up to that time
```

This database only exists on the course server. The script therefore opens a
secure connection (an "SSH tunnel") for you – you just type **two passwords**
when asked (both from `tinf25d-llv.yaml`):

1. `password:` → the **SSH** password (`ssh: passwort:`). The first time, ssh may
   also ask `Are you sure you want to continue connecting?` → type `yes`.
2. `Passwort der Kurs-DATENBANK` → the **postgres** password (`postgres: passwort:`).

`check-history` changes nothing; it only prints a report.

### Watch the history arrive like live data

```bash
python start.py replay-history                 # course database (node 101), one message per minute
python start.py replay-history --csv           # sample recording TSN-002 instead (no SSH needed)
python start.py replay-history --interval 10   # one message every 10 seconds
```

The recorded messages are sent again over MQTT, one after another, exactly like a node would send
them - just faster (node 101: every 15 min, replay: every minute). They arrive as their own device
**`101-sim`** (or `TSN-002-sim`), so they never mix with real data, and you can watch the overview,
chart and warning banner update. Needs **test mode** (`python start.py mode test`), because the replay
goes to the local test broker. The SSH connection is only needed at the start (to load the data);
Ctrl+C stops the replay, everything sent so far stays in the database.

Note: the messages get the time at which they arrive, so the chart is "time-lapse": one hour on the
chart is 60 original messages (= 15 hours of node 101). Day/night shading and the prediction refer to
the replay time, not the original. Paste it to Claude/your team
to decide from when on the data is garbage, then import with `--to`.

## What is where on your computer

| Address | What |
|---|---|
| http://localhost:20800 | the web page |
| http://localhost:20801/docs | the API with clickable documentation |
| `localhost:20832` | the database – e.g. with DBeaver: database `batterywatch`, user `batterywatch`, password = `POSTGRES_PASSWORD` in the file `.env` |
| `localhost:20883` | the local test MQTT broker |

Your settings (incl. passwords) are in the file **`.env`** in the project folder. It was
created by `start.py` and is never uploaded to GitHub. To start over with the
questions, delete `.env` and run `python start.py` again.

## Running the tests

```bash
cd backend
python -m pip install -r requirements-dev.txt   # once
python -m pytest
```

Or in VS Code: the **Testing** panel (flask icon on the left) → *Run Tests*.
Tests that need a database are skipped (that's fine).

## Something doesn't work?

| Message | Meaning / fix |
|---|---|
| `Docker läuft nicht` | start Docker Desktop and wait until it's ready |
| `port is already allocated` | another program uses port 20800–20883; stop it or change `WEB_PORT` etc. in `.env` |
| `cannot reach MQTT broker` in `logs` | no internet, or wrong MQTT password → `python start.py mode real` and type it again |
| page shows no devices | real mode: wait up to 15 min for node 101; test mode: `python start.py` again |
| anything else | `python start.py status` and `docker compose logs <part>` (part = collector, api, db, frontend) |

How all the parts work together: [How-it-works.md](How-it-works.md).
