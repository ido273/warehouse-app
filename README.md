# WarehouseMS — Smart Warehouse Management System

A SaaS platform for managing and monitoring storage locations, suitable for both home and commercial use. Organize boxes and items across multiple workspaces, with role-based access, QR-code lookup, and AI-assisted tagging.

## Architecture

Four Flask microservices behind an ingress, backed by MySQL and AWS (S3 for images, Bedrock for AI tagging):

```
                        Internet
                            │
                   AWS NLB (TLS termination)
                            │
                      nginx-ingress
                            │
                       ┌────▼─────┐
                       │ frontend │  session auth, server-rendered UI, EN/HE i18n
                       └────┬─────┘
                 ┌──────────┼──────────┐
                 │                     │
          ┌──────▼──────┐      ┌───────▼──────┐
          │ auth-service │◄────┤   backend    │
          │ JWT, users,  │     │ items/boxes, │
          │ workspaces   │     │ tags, QR,    │
          └──────┬───────┘     │ CSV/Excel    │
                 │             └───┬──────┬───┘
                 │                 │      │
          ┌──────▼─────────────────▼──┐   │
          │          MySQL             │   │
          └────────────────────────────┘   │
                                    ┌───────▼──────┐        ┌──────────────┐
                                    │  ai-tagging   │───────►  AWS Bedrock  │
                                    └───────────────┘        └──────────────┘
                        backend also talks directly to AWS S3 (box/item images)
```

Each service is independently deployed via its own Helm chart (`<service>/helm/`); `warehouse-gitops` holds the environment values ArgoCD syncs, and `warehouse-infra` provisions the underlying AWS/EKS infrastructure.

## Features

- **Inventory management** — boxes and items with unique codes (`B001`, `I001`), images, quantities, fast search/filter by name/tag/category/location, gallery and list views.
- **QR codes** — every box gets a scannable QR code linking to its (optionally public) contents.
- **Workspaces & roles** — multiple workspaces per user, admin/manager/contributor/viewer roles, invite codes, join-request approval.
- **AI tagging** — optional "Generate Tags" action calls `ai-tagging` (AWS Bedrock) for suggested tags based on item name/image, language-aware per workspace setting.
- **Tracking** — full change history per box/item, last-modified-by tracking.
- **Export** — CSV and Excel export of inventory.
- **Hebrew / English UI** with RTL layout support (see Known limitations for current coverage).

## The 4 microservices

All four are Flask apps, all listening on container port **8080**, all served via gunicorn in production (`gunicorn --bind 0.0.0.0:8080 --workers 2 --threads 4 --timeout 60 app:app`).

| Service | Responsibility | Key dependencies |
|---|---|---|
| **frontend** | Server-rendered UI (Jinja templates), session-based login, proxies API calls to `backend`/`auth-service` with the JWT attached, EN/Hebrew i18n with RTL support | `BACKEND_URL`, `AUTH_SERVICE_URL`, `SECRET_KEY` |
| **backend** | Boxes/items/tags CRUD, box QR codes, image upload to S3, CSV/Excel export, change history, calls `ai-tagging` for tag suggestions | Flask-SQLAlchemy + MySQL, boto3 (S3), qrcode/Pillow, openpyxl |
| **auth-service** | User accounts, JWT issuance/verification, workspaces (multi-tenant), roles (admin/manager/contributor/viewer), invite codes, join requests | Flask-JWT-Extended, Flask-Bcrypt, Flask-SQLAlchemy + MySQL |
| **ai-tagging** | Given an item name (and optional image URL), returns suggested tags via AWS Bedrock (`amazon.nova-lite-v1:0`), with language-aware prompts (English / Hebrew) and a mock fallback if Bedrock is unavailable | boto3 (bedrock-runtime), IRSA for AWS credentials |

## Local development

```bash
cp .env.example .env      # fill in real values
docker compose up -d
```

This starts all 4 services plus a local `mysql:9.7` container. Ports (host → container):

| Service | Host port |
|---|---|
| frontend | 3000 → 8080 |
| backend | 5001 → 8080 |
| ai-tagging | 5002 → 8080 |
| auth-service | 5003 → 8080 |
| mysql | 3306 → 3306 |

`frontend` waits on `auth-service` (healthy); `backend` waits on `mysql` and `auth-service` (healthy) and `ai-tagging` (started). Each service also mounts its source for live-reload in dev.

For the MySQL Helm chart used in-cluster, create a local (gitignored) values file instead of editing the example:
```bash
cp mysql/helm/values-local.example.yaml mysql/helm/values-local.yaml
# then edit values-local.yaml with real passwords
```

## Environment variables

See `.env.example` at the repo root for the full local-dev template. Summary of what each service reads:

- **frontend**: `SECRET_KEY` (required — Flask session signing), `AUTH_SERVICE_URL`, `BACKEND_URL`, `SESSION_COOKIE_SECURE` (default `true`, set `false` for local HTTP)
- **backend**: `DATABASE_URL`, `AUTH_SERVICE_URL`, `AI_TAGGING_URL`, `FRONTEND_BASE_URL` (used to build QR-code URLs), `S3_BUCKET_NAME`, `S3_REGION` (default `eu-west-1`), `MAX_UPLOAD_BYTES` (default 10MB)
- **auth-service**: `DATABASE_URL` (required), `JWT_SECRET_KEY` (required), `JWT_ACCESS_TOKEN_MINUTES` (default 60)
- **ai-tagging**: `BEDROCK_REGION` (default `eu-west-1`), `BEDROCK_MODEL_ID` (default `amazon.nova-lite-v1:0`)

In production, secrets (`SECRET_KEY`, `JWT_SECRET_KEY`, `DATABASE_URL`, S3 IRSA role) come from Kubernetes Secrets provisioned by `warehouse-infra` (Terraform), not from committed files.

## CI/CD flow

Three GitHub Actions workflows under `.github/workflows/`:

- **`ci.yaml`** — runs on **every push, every branch**. For each of the 4 services: flake8 lint, `docker build` the image, run the container against a `mysql:8` service container with test env vars, and curl `/health`. Build + smoke-test only — nothing is pushed to a registry.
- **`build-service.yml`** — a reusable workflow (`workflow_call`) that logs into AWS ECR and does a multi-arch `docker buildx build --platform linux/amd64,linux/arm64 ... --push` for one service. Called by `cd.yaml`, not triggered directly.
- **`cd.yaml`** — runs only on **push to `master`**. Builds and pushes all 4 images to ECR (tagged with the commit SHA) via `build-service.yml`, then clones `warehouse-gitops`, bumps the `tag:` field in each `envs/production/<service>-values.yaml`, and commits/pushes (with a rebase-and-retry loop to handle concurrent CD runs). ArgoCD then picks up the new tags and syncs the cluster.

So: every branch gets linted and smoke-tested; only `master` triggers a real deploy, and the deploy is a two-repo handoff (this repo → `warehouse-gitops` → ArgoCD).

## Branching strategy

This repo uses **trunk-based, feature-branch-per-PR** — not GitFlow. There is no `develop` or `release/*` branch, and none has existed in this repo's history.

- `master` is the single long-lived branch, protected (no direct pushes — PRs required).
- Work happens on short-lived `feat/*`, `fix/*`, or `chore/*` branches, each usually scoped to one change, merged into `master` via PR.
- `cd.yaml` treats every `master` push as deployable — merging a PR ships it.

Adopting real GitFlow (`develop` as the integration branch, `release/*` branches, hotfixes off `master`) would be a deliberate process change on top of what's here today.

## Known limitations

- **No automated test suite.** CI lints and boots each container, then hits `/health` — there's no unit/integration test coverage.
- **JWT revocation blocklist is in-process**, not shared (e.g. Redis) — doesn't survive a pod restart and doesn't work correctly across multiple `auth-service` replicas.
- **Hebrew i18n coverage is partial.** Core chrome (navbar, item/box create-edit, auth pages) is translated; several content pages and admin modals still render in English regardless of language setting — see `hebrew_i18n_followup.md`.
- **Single environment.** Only a `production` values set exists in `warehouse-gitops` — no staging/dev environment is deployed.
- **Local dev MySQL** uses plain root/user credentials from `.env` — fine for `docker compose`, not a pattern to carry into production.
