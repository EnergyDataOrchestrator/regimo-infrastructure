# regimo-infrastructure
Regimo-Infrastructure: Deployment and configuration-as-code for the Regimo Orchestrator. Manages the Kafka bus, container orchestration, and system monitoring.

## Overview
The `regimo-infrastructure` repository provides the operational foundation for the **Regimo Energy Data Orchestrator**. It contains the configuration-as-code required to deploy and manage the **Kafka event bus**, Zookeeper/KRaft clusters, and the containerised environment utilised by the **Karlsruhe Institute of Technology (KIT)** research team.

## Core Responsibilities
While other repositories house the system logic (referencing **KITopen-ID: 1000168804**), this repository defines the **runtime environment**:

* **Message Broker Management:** Deployment configurations for Apache Kafka, including topic definitions, retention policies, and security protocols.
* **Orchestration Deployment:** Docker Compose files and Kubernetes manifests for launching the full suite of ontology-aware sockets.
* **Network Topology:** Configuration of the internal virtual networks that facilitate low-latency communication between energy microservices.
* **Monitoring Stack:** Integration of tools (such as Prometheus and Grafana) to visualise the throughput of the Kafka bus and the health of the individual sockets.



## Repository Contents
* `Servers/`: Local RDMO development instances (see below).
* `fuseki-proto/`: Containerised Apache Jena Fuseki graph-database stack with the `fuseki-proto` maintenance CLI (see below).
* `docker/`: Standardised Dockerfiles and `docker-compose.yml` blueprints for local development and laboratory deployment.
* `k8s/`: (Optional) Kubernetes Helm charts or manifests for scaling the orchestrator in cloud environments.
* `config/`: Centralised configuration files for Kafka brokers and the Regimo message schema registry.
* `scripts/`: Maintenance scripts for resetting the bus state, performing bulk data migrations or installing RDMO plugins (`install_madmp_exporter.py`).

## Graph database (`fuseki-proto`)
The `fuseki-proto/` directory hosts the internal **graph database**: an Apache Jena **Fuseki Full** instance built from source (Apache publishes no registry image), serving

* **`/projects`** — TDB2 dataset with the internal-format project graphs (persisted),
* **`/shapes`** — in-memory dataset with the SHACL project-claim shapes.

Compose auto-merges nothing — the host port is declared directly in `docker-compose.yml`, so the stack serves on host port **3031** (3030 stays reserved for a system-managed Fuseki).

```bash
# from the edo root (the CLI lives in the shared edo venv):
uv run fuseki-proto start    # build + up + seed /shapes → http://localhost:3031/ (web UI)
# or manually from fuseki-proto/:
docker compose build
docker compose up -d
```

The `fuseki-proto` CLI (installed editable into the edo root venv via `pyproject.toml`, see `fuseki-proto/tool/`) covers lifecycle (`start/status/ping/stop`), backup/restore, loading instance graphs, and the maDMP→internal-format round trips (`trip`, `agnostic-trip`) and RO-Crate generation (`crate`). See `fuseki-proto/README.md` and `fuseki-proto/tool/README.md`.

## Local RDMO dev instance (`Servers/rdmo-app`)
The `Servers/` directory hosts the local **RDMO** (Research Data Management Organiser) development instance. It is a clone of the official project skeleton [`rdmorganiser/rdmo-app`](https://github.com/rdmorganiser/rdmo-app), set up with:

* `env/` — Python 3.12 virtualenv with `rdmo` (2.5.x) installed (`uv pip install rdmo`)
* `config/settings/local.py` — development configuration: `DEBUG = True`, SQLite database, `ALLOWED_HOSTS` for localhost, superuser `admin` / `admin`
* `db.sqlite3` — fully migrated dev database

> The virtualenv, `local.py`, and the SQLite database are git-ignored by rdmo-app's `.gitignore`, so a fresh clone starts empty.

### Start the dev instance

```bash
cd Servers/rdmo-app
source env/bin/activate
python manage.py runserver        # → http://127.0.0.1:8000/
```

Sign in at `http://127.0.0.1:8000/` with `admin` / `admin` (local dev only).
The maDMP export plugin used by the sync engine (`regimo-core`) lives in
`components/socket-rdmo/madmp-exporter/`; install it into this instance with
the admin script (from the repo root, idempotent — installs the package,
registers the plugin, wires the `GET /api/v1/madmp/projects/{pk}/` API route
and verifies the result; see that package's README for troubleshooting):

```bash
python3 scripts/install_madmp_exporter.py          # add --create-token admin for machine access
```

Note: `uv pip install` needs the exporter's `pyyaml` dep present in the env;
the script re-runs the editable install automatically whenever the probe fails.

### Rebuild from scratch (e.g. after a fresh clone)

```bash
cd Servers/rdmo-app
uv venv --python 3.12 env
uv pip install --python env/bin/python rdmo
cp config/settings/sample.local.py config/settings/local.py   # then edit to taste
env/bin/python manage.py migrate
env/bin/python manage.py createsuperuser
env/bin/python manage.py runserver
```

## Usage
This repository is the primary starting point for any deployment of the **EDO**. By cloning this repository and executing the provided orchestration scripts, researchers can instantly establish a fully functional environment where new sockets can be tested and integrated into the live data stream.
