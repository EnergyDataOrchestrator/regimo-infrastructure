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
* `docker/`: Standardised Dockerfiles and `docker-compose.yml` blueprints for local development and laboratory deployment.
* `k8s/`: (Optional) Kubernetes Helm charts or manifests for scaling the orchestrator in cloud environments.
* `config/`: Centralised configuration files for Kafka brokers and the Regimo message schema registry.
* `scripts/`: Maintenance scripts for resetting the bus state or performing bulk data migrations.

## Usage
This repository is the primary starting point for any deployment of the **EDO**. By cloning this repository and executing the provided orchestration scripts, researchers can instantly establish a fully functional environment where new sockets can be tested and integrated into the live data stream.
