# Movie Watchlist — README (DevOps Deployment Guide)

## Table of Contents

1. Project Overview
2. Repo layout (files & purpose)
3. Prerequisites (local & production)
4. Environment variables and secrets
5. Local development / testing (Docker Compose)
6. Production deployment (recommended: Docker Swarm)

   * a) Create networked volume (NFS example)
   * b) Create Docker secrets
   * c) Deploy stack
7. Healthchecks, resources, restart policies, and placement
8. Persistent storage & backups (Postgres)
9. Networking & security (firewall, TLS, secrets, users)
10. Logging & monitoring (suggested stack)
11. CI/CD pipeline overview (suggested flow)
12. Kubernetes (optional) — high-level guide
13. Common troubleshooting & diagnostics
14. Useful commands & tips
15. Files referenced in this repo
16. Appendix: example commands

---

## 1. Project Overview

**Movie Watchlist** is a small 3-tier application:

* **Frontend:** static HTML/CSS/JS served by Nginx (container).
* **API:** Python Flask app using SQLAlchemy (container).
* **Database:** PostgreSQL (container), stores `movies` table with `id, title, genre, status, image_url`.

It’s containerised using Docker and orchestrated via Docker Compose for local use and recommended to run on **Docker Swarm** (or Kubernetes for larger setups) in production.

---

## 2. Repo layout

```
movie-watchlist/
├─ frontend/
│  ├─ Dockerfile
│  └─ index.html
├─ api/
│  ├─ Dockerfile
│  ├─ requirements.txt
│  └─ app.py
├─ docker-compose.yml
└─ .env
```

* `docker-compose.yml` — Compose file describing `frontend`, `api`, `postgres` services.
* `api/` — Flask app code and Dockerfile.
* `frontend/` — static UI and Dockerfile (nginx).
* `.env` — environment variables (DB creds). **Do not commit** real secrets.

---

## 3. Prerequisites

### Local dev

* Docker (v20.10+) and Docker Compose plugin (`docker compose`)
* Linux / macOS / Windows WSL2 with Docker support
* Ports: 8080 (frontend), 5000 (api) available on host

### Production (recommended)

* Multiple hosts (manager/worker) for Docker Swarm OR Kubernetes cluster
* NFS/Ceph/Longhorn/Cloud block storage for persistent DB volumes
* Reverse proxy / ingress (Traefik, nginx, or cloud LB) with TLS
* Monitoring (Prometheus/Grafana), logging stack (EFK/ELK or cloud provider logs)
* CI/CD system (GitHub Actions / GitLab CI / Jenkins) to build/push images to registry

---

## 4. Environment variables & secrets

**`.env` example (DO NOT COMMIT real passwords):**

```
DB_USER=appuser
DB_PASSWORD=supersecret
DB_NAME=moviedb
```

**Production best-practices**

* Use Docker secrets / Vault / cloud secrets manager for DB password.
* DO NOT store plaintext credentials in git.

---

## 5. Local development / testing (Docker Compose)

From repo root:

1. Build & run:

```bash
docker compose up -d --build
```

2. Verify:

* Frontend: `http://localhost:8080`
* API: `http://localhost:5000/movies`
* Check logs:

```bash
docker compose logs -f api
docker compose logs -f postgres
```

3. Stop and remove (note: `-v` removes volumes):

```bash
docker compose down
# or to remove volumes
docker compose down -v
```

4. DB reset:

```bash
docker compose down -v
docker compose up -d --build
```

---

## 6. Production deployment (recommended: Docker Swarm)

Below are production-level steps using Docker Swarm and an NFS network volume as persistent storage for Postgres. If you use cloud managed DB, skip Postgres container and point `DATABASE_URL` to managed DB.

### a) Initialize Swarm (on manager)

```bash
docker swarm init --advertise-addr <MANAGER_IP>
```

Add worker nodes with the token printed by the init command.

### b) Create NFS export (Storage server)

*On your storage server (example IP `192.0.2.10`):*

```bash
sudo apt update
sudo apt install -y nfs-kernel-server
sudo mkdir -p /srv/docker-volumes/moviedb
sudo chown nobody:nogroup /srv/docker-volumes/moviedb
echo "/srv/docker-volumes/moviedb 10.0.0.0/24(rw,sync,no_subtree_check,no_root_squash)" | sudo tee -a /etc/exports
sudo exportfs -ra
sudo systemctl restart nfs-kernel-server
```

Adjust subnet & export options for your environment. For production consider high-availability storage (Ceph, Gluster, Longhorn, cloud PVs).

### c) Create Docker volume using NFS (on each node that may run Postgres)

```bash
docker volume create \
  --driver local \
  --opt type=nfs \
  --opt o=addr=192.0.2.10,rw,nfsvers=4,hard,timeo=600,retrans=2 \
  --opt device=:/srv/docker-volumes/moviedb \
  moviedb_pgdata
```

### d) Create Docker secret for DB password

```bash
echo "PRODUCTION_DB_PASSWORD" | docker secret create db_password -
```

*Note:* the provided Compose in repo uses env vars; for Swarm, prefer using `secrets` and not environment variables. You may need to adapt `docker-compose.yml` to a `docker-stack.yml` with `secrets:` references and `deploy:` options.

### e) Deploy stack

Convert `docker-compose.yml` to use `deploy:` preferences (replicas, resources, placements). Example deploy command:

```bash
docker stack deploy -c docker-compose.yml movie-watchlist
```

### f) Post-deploy checks

```bash
docker stack ps movie-watchlist
docker service ls
docker service logs movie-watchlist_api --follow
docker volume inspect moviedb_pgdata
```

---

## 7. Healthchecks, resources, restart policies, and placement

* Add `healthcheck` to API and Postgres services so orchestrator restarts unhealthy containers.
* Use `deploy.resources` (limits & reservations) in Swarm Compose to prevent noisy neighbors.
* Use `placement` constraints/affinities to control where DB runs (e.g., avoid running DB on manager node).

Example snippet (`deploy:`) to include in Swarm stack:

```yaml
deploy:
  replicas: 2
  resources:
    limits:
      cpus: '0.50'
      memory: 512M
  placement:
    constraints:
      - node.role == worker
  restart_policy:
    condition: on-failure
    max_attempts: 5
```

---

## 8. Persistent storage & backups (Postgres)

**Data location:** inside Docker volume mapped to `/var/lib/postgresql/data`.

### Backup strategies

1. **Logical backup (pg\_dump):**

```bash
docker exec -t <postgres_container> pg_dump -U <user> <db> > backup.sql
# or from host using psql client pointed to DB host/port
```

2. **Filesystem snapshot:** snapshot the underlying NFS/volume (ensure DB flushed or use filesystem snapshot quiesce).
3. **Automated scheduled backups:** run a cron job container that performs `pg_dump` and uploads to S3/compatible storage.

### Restore

```bash
cat backup.sql | docker exec -i <postgres_container> psql -U <user> -d <db>
```

**Important:** Test backups & restores regularly.

---

## 9. Networking & security

* Use private overlay networks (Swarm) or Kubernetes NetworkPolicies to restrict traffic.
* Reverse proxy (Traefik/nginx) for TLS termination and routing to frontend/API.
* Use strong passwords and rotate regularly.
* Use secrets manager (Vault, AWS Secrets Manager) for production secrets.
* Limit API access using authentication (JWT/Session) before exposing to public.
* Open only necessary ports on firewall: 80/443 for reverse proxy, SSH for ops, nothing else public.

---

## 10. Logging & monitoring

* **Logs:** Use centralized logging (Fluentd/Logstash Filebeat) → Elasticsearch / Loki. Configure container logs with `max-size` and `max-file`.
* **Metrics:** Export metrics from containers and host (cAdvisor, node\_exporter), collect in Prometheus, visualize in Grafana.
* **Alerts:** Configure alerting (Prometheus Alertmanager) for DB down, high CPU, low disk space.
* **Health pages:** API has `/healthz` route — configure probe checks.

---

## 11. CI/CD pipeline (suggested)

1. On Push to `main`: run tests (lint, unit), build Docker images, run security scan (Trivy).
2. Push images to registry (Docker Hub / ECR / GCR / private registry).
3. Deploy to staging:

   * Pull new images and `docker stack deploy` to staging cluster OR update K8s manifests.
4. Run smoke tests.
5. If success, promote to production (tag & deploy).
6. Use canary or blue/green deploy strategy for production.

Example GitHub Actions steps:

* `build` -> `scan` -> `push` -> `deploy-staging` -> `smoke-tests` -> `deploy-prod`.

---

## 12. Kubernetes (optional / advanced)

If you choose Kubernetes:

* Use Deployment + Service for API and frontend.
* Use StatefulSet for Postgres with PersistentVolumeClaim (PVC) and a CSI driver (Ceph, Longhorn, cloud PV).
* Use Ingress controller (Traefik / nginx) for TLS routing.
* Use Secrets for DB credentials.
* Readiness and liveness probes for API and Postgres.
* Example resources you’ll need to create: `Deployment`, `Service`, `Ingress`, `Secret`, `ConfigMap`, `PVC`, `StatefulSet` (for Postgres).

---

## 13. Common troubleshooting & diagnostics

* **API can't connect to DB:**

  * Check `docker compose logs api` / `docker service logs`.
  * Check `DATABASE_URL` env var; on Swarm, ensure service name `postgres` resolvable.
  * Confirm Postgres container healthy: `pg_isready` inside container.

* **Postgres permission denied when using NFS:**

  * Check `no_root_squash` and UID/GID mapping. Postgres runs as `postgres` user inside container — align ownership on NFS export.

* **Frontend shows blank / CORS error:**

  * Ensure API port reachable and `flask-cors` enabled.
  * If using reverse proxy, ensure routing path correct and headers preserved.

* **Data lost after recreate:**

  * Verify `pgdata` volume exists and is mounted (`docker volume inspect pgdata`).
  * If volume removed with `docker compose down -v`, data will be deleted.

---

## 14. Useful commands

Local:

```bash
docker compose up -d --build
docker compose logs -f api
docker compose exec api bash
docker compose exec postgres psql -U appuser -d moviedb
```

Swarm:

```bash
docker swarm init --advertise-addr <IP>
docker stack deploy -c docker-compose.yml movie-watchlist
docker stack ps movie-watchlist
docker service ls
docker service logs movie-watchlist_api --follow
```

Volume (NFS create):

```bash
docker volume create --driver local \
  --opt type=nfs \
  --opt o=addr=192.0.2.10,rw,nfsvers=4 \
  --opt device=:/srv/docker-volumes/moviedb \
  moviedb_pgdata
```

Secret:

```bash
echo "PROD_DB_PASSWORD" | docker secret create db_password -
```

Backup:

```bash
docker exec -t <postgres_container> pg_dump -U appuser moviedb > backup.sql
```

---

## 15. Files referenced in repo

* `docker-compose.yml` — service definitions (frontend, api, postgres)
* `frontend/index.html` — UI code, points to `http://localhost:5000` API by default
* `api/app.py` — Flask API, table creation, preload Nolan movies
* `api/requirements.txt` — Python deps
* `api/Dockerfile`, `frontend/Dockerfile` — container builds
* `.env` — database credentials (for local use)

---

## 16. Appendix: example production stack tips & checklist

### Quick production checklist

* [ ] Use secrets manager (do not commit `.env` to git with real creds).
* [ ] Use HA storage (Ceph/Longhorn) for DB PV.
* [ ] Configure TLS on ingress (Let’s Encrypt via Traefik or managed certs).
* [ ] Setup monitoring & alerting (Prometheus/Grafana).
* [ ] Setup centralized logging (ELK/Loki).
* [ ] Setup automated backups & daily restore tests.
* [ ] Harden Docker hosts (userns remap, least privileges, firewall).
* [ ] Scan images with Trivy or another scanner.
* [ ] Use resource limits and node placement constraints.

---

## Contact / Maintainer notes

If anything fails during deployment, gather:

* `docker compose ps` / `docker service ps` output
* `docker logs` of failing service(s)
* `docker volume inspect` for volume info
* Network connectivity checks (DNS resolution between containers)

