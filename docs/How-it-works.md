# How BatteryWatch works – explained from zero

This page explains **every part of the system**: what it is, where it runs,
which port it uses and how the parts talk to each other.
If you only read one document, read this one.

---

## 1. The idea in three sentences

Traffic lights run on batteries. A small box on each light (a **node**, e.g. node `101`)
measures the battery's voltage and current every 15 minutes and sends the numbers over
the internet. **BatteryWatch** receives these numbers, stores them and shows on a
web page how full each battery is, so a technician can swap it before it's empty.

---

## 2. The big picture

```
 ┌──────────────────────┐
 │ Node 101             │  on a traffic light, somewhere outside
 │ measures every 15 min│
 └──────────┬───────────┘
            │ (1) MQTT message to topic  traffic-nodes/101/measurements
            │     {"current_mA": 620, "voltage_mV": 12100, "temperature_C": 17, ...}
            ▼
 ┌──────────────────────────────┐
 │ Course MQTT broker           │  run by the course, NOT by us
 │ mqtt.ti-labs.ai  port 8883   │  ("post office" for messages, encrypted, needs a password)
 └──────────┬───────────────────┘
            │ (2) forwards every message to everyone who subscribed
            ▼
 ╔═════════════════════════════════════════════════════════════════════════════╗
 ║ COURSE SERVER 212.227.31.76   (we log in with: ssh tinf25d-llv@212.227.31.76) ║
 ║                                                                               ║
 ║   Our Docker containers (folder ~/batterywatch, started by docker compose):   ║
 ║                                                                               ║
 ║   ┌─────────────┐ (3) saves  ┌──────────────┐                                 ║
 ║   │ collector   │──────────▶│ db           │◀──── server port 20832          ║
 ║   │ (Python)    │  messages │ (PostgreSQL) │      (only from the server /     ║
 ║   └─────────────┘           └──────┬───────┘       via SSH tunnel)            ║
 ║                                    │ (5) reads                                ║
 ║                             ┌──────┴───────┐                                  ║
 ║                             │ api          │◀──── server port 20801          ║
 ║                             │ (Python)     │      (only from the server)      ║
 ║                             └──────▲───────┘                                  ║
 ║                                    │ (4b) /api/... is forwarded               ║
 ║                             ┌──────┴───────┐                                  ║
 ║                             │ frontend     │◀──── server port 20800  ◀────────╫── (4a) your browser
 ║                             │ (nginx+React)│      (from the INTERNET)         ║    http://212.227.31.76:20800
 ║                             └──────────────┘                                  ║
 ║   ┌─────────────┐                                                             ║
 ║   │ mqtt        │ our OWN test broker, port 20883 (only for fake test data)   ║
 ║   └─────────────┘                                                             ║
 ║                                                                               ║
 ║   Course history database  127.0.0.1:5432  (belongs to the course; we only    ║
 ║   read it ONCE to copy the old measurements, deploy/import-history.sh)        ║
 ╚═══════════════════════════════════════════════════════════════════════════════╝
```

**Read it like this:**
1. Node 101 sends its numbers to the course broker.
2. The broker forwards them to everyone listening, including our **collector**.
3. The collector checks the message and saves it in our database **db**.
4. You open the web page. The **frontend** sends you the page; the page then asks
   for data at `/api/...`, which nginx forwards to the **api**.
5. The api reads the database, calculates the battery % and answers.

---

## 3. All ports at a glance

A **port** is like an apartment number on a computer: one address (the server),
many programs, each behind its own number. Our group may only use server
ports **20800–20899**.

Every container also has its **own internal** port (the program's usual number).
`docker-compose.yml` connects them: `"20800:80"` = server port 20800 leads to port 80 in the container.

| Server port | → Container : port | What is it | Who can reach it |
|---|---|---|---|
| **20800** | frontend : 80 | the web page (and `/api/…` passed on to the api) | **everyone** (internet) – `http://212.227.31.76:20800` |
| 20801 | api : 8000 | the REST API, docs at `/docs` | only the server itself (127.0.0.1) |
| 20832 | db : 5432 | our PostgreSQL database | only the server itself, or the internet if `DB_BIND=0.0.0.0` |
| 20883 | mqtt : 1883 | our own test MQTT broker | only the server itself |
| – | collector | opens no port, only connects **out** | – |

Ports **outside** our system:

| Address | What | Notes |
|---|---|---|
| `mqtt.ti-labs.ai:8883` | course MQTT broker (real nodes) | encrypted (TLS), user `tinf25d-llv` + password |
| `212.227.31.76:22` | SSH login to the course server | user `tinf25d-llv` + password |
| `127.0.0.1:5432` on the server | course history database `measurements` | only from the server itself |
| `tile.openstreetmap.org` | map pictures | loaded by **your browser** directly |

**"Only the server itself" (127.0.0.1)** means: programs on the server can connect,
the internet can't. From your laptop you get there with an **SSH tunnel**:

```bash
ssh -L 20832:127.0.0.1:20832 -L 20801:127.0.0.1:20801 tinf25d-llv@212.227.31.76
```

While that window stays open, `localhost:20832` on your laptop **is** our database
(DBeaver, pgAdmin) and `http://localhost:20801/docs` is the API documentation.

**Inside Docker, containers call each other by name**, not by IP:
the collector connects to `db:5432`, nginx forwards to `api:8000`.

---

## 4. Following one message, step by step

Node 101 sends at 09:37:

**① Node → course broker.** Topic `traffic-nodes/101/measurements`, content:
```json
{"current_mA": 620, "voltage_mV": 12100, "temperature_C": 17, "lat": null, "lon": null,
 "altitude_m": null, "satellites": null, "time": null}
```
Units: **milli**volt and **milli**ampere – 12100 mV = 12.1 V.

**② Broker → collector.** Our collector subscribed to `traffic-nodes/+/measurements`
(`+` = any node), so the broker hands it the message.
→ `backend/batterywatch/collector/main.py`, method `on_message`.

**③ Check.** `backend/batterywatch/contract.py`, `parse_message`:
- topic → device id `101`
- text → JSON → every field checked (is `voltage_mV` a number between 0 and 60000? …)
- `"time": null` → the receive time is used

If something's wrong (node 101 currently sends `voltage_mV: 5368709120`, which is
5.4 *million* volts, a read error), the reason is written down and the message is
**not** turned into a measurement.

**④ Save.** `backend/batterywatch/db.py`, `save_message`:
- table `devices`: add `101` if it's new
- table `raw_messages`: the message exactly as received + valid yes/no + reason
- table `measurements` (valid messages only): the values plus the corrected battery voltage
  `U_bat = 0.002 Ω × 620 mA + 12100 mV = 12101.24 mV` (`battery.py`)

**⑤ Web page.** Within 5 minutes your open page asks `GET /api/devices`.
`backend/batterywatch/api/main.py` reads the database (`api/queries.py`):
- average voltage of the last 60 minutes → e.g. 12.10 V
- 12.10 V on the curve 10.5 V = 0 % … 12.7 V = 100 % → **73 %** (`battery.py`)
- 73 % ≥ 50 % → status **"ok"** → green

**⑥ Display.** `frontend/src/pages/Overview.jsx` draws the row "73 %" with a green battery.

---

## 5. What happens when you open the web page

1. Browser → `http://212.227.31.76:20800` → the **frontend** container (nginx).
2. nginx sends `index.html` plus the JavaScript and CSS files (built from `frontend/src/`).
3. The JavaScript starts (`main.jsx` → `App.jsx`) and asks `GET /api/devices`.
4. nginx sees `/api/` and passes it to `api:8000` (`frontend/nginx.conf`).
5. The api answers with JSON, the page draws the list and the map.
6. Every 5 minutes, steps 3–5 repeat by themselves (`usePolling.js`).
7. Clicking a device → address `/geraete/101` → `DeviceDetail.jsx` asks for
   `/api/devices/101`, `/history` and `/messages`.

---

## 6. Where is what (folders)

```
Software_Engineering_Semesterprojekt/
├── docker-compose.yml        ← THE overview: all containers, ports, settings
├── .env.example              ← template for the settings (copy to .env, add passwords)
├── .env                      ← real settings + passwords (only on the server, NOT in Git)
├── mosquitto/mosquitto.conf  ← settings of our own test broker
├── deploy/
│   ├── setup-server.sh       ← sets everything up on the server
│   └── import-history.sh     ← copies the old data from the course database
├── backend/                  ← all Python code (collector + api + tools)
│   ├── Dockerfile            ← recipe for the Python image
│   ├── requirements.txt      ← Python libraries we use
│   ├── batterywatch/
│   │   ├── config.py         ← reads the settings
│   │   ├── contract.py       ← what a valid message looks like
│   │   ├── battery.py        ← mV → corrected voltage → % → red/yellow/green
│   │   ├── schema.sql        ← database tables
│   │   ├── db.py             ← writing into the database
│   │   ├── collector/        ← PROGRAM: MQTT → database
│   │   ├── api/              ← PROGRAM: database → JSON for the page
│   │   └── tools/            ← test publisher (fake nodes), import tool
│   └── tests/                ← automatic tests (pytest)
├── frontend/                 ← the web page (React)
│   ├── Dockerfile, nginx.conf
│   └── src/
│       ├── main.jsx, App.jsx ← start + frame
│       ├── api.js            ← all requests to the backend
│       ├── pages/            ← Overview.jsx, DeviceDetail.jsx
│       └── components/       ← battery icon, map, chart
└── docs/                     ← documentation (you are here)
```

Every code file starts with a comment explaining what it does and who uses it.

---

## 7. Where are the passwords?

| Password | Where it's stored | Used by |
|---|---|---|
| SSH (server login) | nowhere – you type it when logging in | you |
| MQTT (course broker) | `.env` on the server (`COLLECTOR_MQTT_PASSWORD`) | collector |
| Our database | `.env` on the server (`POSTGRES_PASSWORD`, random) | collector, api, you (DBeaver) |
| Course history DB | nowhere – typed into `import-history.sh` | import, once |

`.env` and `tinf25d-llv.yaml` are in `.gitignore` and are **never** uploaded to GitHub.
Show our database password on the server: `grep POSTGRES_PASSWORD .env`

---

## 8. Dictionary

| Word | Meaning here |
|---|---|
| **Node / TrafficNode** | the measuring box on a traffic light (e.g. `101`) |
| **MQTT** | a simple way to send small messages over the internet |
| **Broker** | the MQTT "post office": receives messages and forwards them to subscribers |
| **Topic** | the "address" of a message, e.g. `traffic-nodes/101/measurements`; `+` = wildcard |
| **Publish / Subscribe** | send a message to a topic / ask the broker for all messages of a topic |
| **QoS** | delivery guarantee: 0 = "send and forget" (node 101), 1 = "at least once" |
| **TLS** | encryption of a connection (port 8883 = MQTT with TLS) |
| **Payload / JSON** | the content of a message; JSON = text format `{"name": value, ...}` |
| **Container** | a sealed mini-computer running one program (Docker) |
| **Image** | the frozen template a container is started from (built from a `Dockerfile`) |
| **Docker Compose** | starts several containers together (`docker-compose.yml`) |
| **Volume** | Docker-managed storage that survives restarts (our database data) |
| **Port** | number that says which program on a computer you want to talk to |
| **127.0.0.1 / localhost** | "this computer itself" |
| **SSH / SSH tunnel** | secure remote login; a tunnel makes a server port appear on your laptop |
| **PostgreSQL / SQL** | our database / the language to ask it questions |
| **API / REST / endpoint** | a web server that returns data; an endpoint is one address like `/api/devices` |
| **nginx** | the web server that delivers our page and forwards `/api/...` |
| **React** | JavaScript library our web page is built with |
| **Polling** | asking for new data again and again (every 5 minutes) |
| **mV / mA** | millivolt / milliampere (1000 mV = 1 V). The nodes send mV and mA |
| **Shunt** | small resistor (0.002 Ω) the node measures behind → `U_bat = 0.002 Ω × I + U` |
| **SoC** | "state of charge" = battery level in % |
| **Stale** | no valid measurement for > 45 minutes → shown in red |

---

## 9. "How do I …?" (on the server, in the `batterywatch` folder)

| I want to … | Command |
|---|---|
| see what's running | `docker compose ps` |
| watch incoming messages | `docker compose logs -f collector` (Ctrl+C to stop watching) |
| see API errors | `docker compose logs -f api` |
| look into the database | `docker compose exec db psql -U batterywatch batterywatch` then e.g. `SELECT * FROM devices;` (`\q` quits) |
| see the newest messages | in psql: `SELECT received_at, accepted, error FROM raw_messages ORDER BY id DESC LIMIT 10;` |
| install a new version | `git pull && ./deploy/setup-server.sh` |
| change a setting | edit `.env` (e.g. `nano .env`), then `docker compose up -d` |
| restart everything | `docker compose restart` |
| stop everything (keep data) | `docker compose down` |
| ⚠️ delete ALL data | `docker compose down -v` |

More: [Server.md](Server.md) (setup), [Entwicklung.md](Entwicklung.md) (development, tests),
[MQTT-Vertrag.md](MQTT-Vertrag.md) (message format), [Statusregeln.md](Statusregeln.md) (battery rules).
