# Hardcoded Values Scan

Scope: warehouse-app, warehouse-infra, warehouse-gitops. Checked for hardcoded
URLs, bucket names, regions, account IDs, passwords/secrets, service URLs,
cluster names, and domain names.

## Fixed

| File | What was hardcoded | Fix |
|---|---|---|
| `warehouse-app/backend/app.py:36` | `S3_REGION = "eu-west-1"` | `S3_REGION = os.environ.get("S3_REGION", "eu-west-1")` |
| `warehouse-app/ai-tagging/app.py:12` | `BEDROCK_REGION = "eu-west-1"` | `BEDROCK_REGION = os.environ.get("BEDROCK_REGION", "eu-west-1")` |
| `warehouse-app/ai-tagging/app.py:13` | `BEDROCK_MODEL_ID = "amazon.nova-lite-v1:0"` | `BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")` (bundled with the region fix — same file, same class of issue: model swaps no longer need a code change) |
| `warehouse-infra/modules/eks/main.tf:95` | `Resource = "arn:aws:s3:::warehouse-images-ido273/*"` in the `backend_s3` IAM policy | Added `variable "s3_bucket_name"` to `modules/eks/variables.tf`, changed the resource to `arn:aws:s3:::${var.s3_bucket_name}/*`, wired `s3_bucket_name = module.s3.bucket_name` in root `main.tf` so the policy always tracks the actual bucket the `s3` module creates instead of a duplicated literal |

## Reviewed, no fix needed (already the correct config layer)

| File | What's there | Why it's fine |
|---|---|---|
| `warehouse-app/backend/app.py:17-18` | `DATABASE_URL` default `mysql+pymysql://root:root@localhost/warehouse` | Already `os.environ.get("DATABASE_URL", ...)` — the literal is a local-dev-only fallback; production always supplies `DATABASE_URL` via the `app-secrets` k8s Secret (see `warehouse-gitops/envs/production/backend-values.yaml`) |
| `warehouse-app/*/app.py` (`AUTH_SERVICE_URL`, `AI_TAGGING_URL`, `FRONTEND_BASE_URL`, `BACKEND_URL`) | Service URLs | Already `os.environ.get("X", "http://...")` pattern |
| `warehouse-app/frontend/app.py:18`, `warehouse-app/auth-service/app.py:19` | `SECRET_KEY`, `JWT_SECRET_KEY` | Required via `os.environ["X"]` with no default — fails closed if unset, sourced from k8s Secrets in gitops values, never a literal |
| `warehouse-app/backend/helm/values.yaml` | Bucket name, account ID in `eks.amazonaws.com/role-arn` | This is the chart's values file — the designated place for concrete config; templates already consume it via `.Values.xxx` |
| `warehouse-infra/variables.tf` | `region` (`eu-west-1`), `cluster_name` (`warehouse-cluster`), `domain_name` (`warehousems.online`) defaults | These are the variable *declarations* — this is where such defaults are supposed to live; all other `.tf` files reference `var.region` / `var.cluster_name` / `var.domain_name`, not the literals |
| `warehouse-infra/modules/s3/variables.tf:9` | `bucket_name` default `warehouse-images-ido273` | Same as above — the variable's default value declaration |
| `warehouse-infra/backend.tf:5` | `region = "eu-west-1"` in the `terraform { backend "s3" {} }` block | Cannot be parametrized — Terraform backend configuration blocks do not support variable interpolation (hard language limitation). Literal value, or `-backend-config` file at `terraform init`, are the only options |
| `warehouse-gitops/envs/production/*.yaml` | Account ID, region, bucket name, domain, service URLs (`http://backend:8080`, etc.) | These values files *are* the per-environment config surface for the charts (all consumed via `.Values.xxx` / the `env:` list in templates). Secrets (`JWT_SECRET_KEY`, `DATABASE_URL`, `SECRET_KEY`) are already sourced via `secretKeyRef`, never plaintext. No hardcoding to extract — nothing changed, nothing to commit here |

## Not found
No hardcoded passwords/API keys in plaintext, no `localhost` outside dev-only
fallback defaults, no domain name (`warehousems.online`) hardcoded in
application or Terraform code (only in the `var.domain_name` default and
gitops values, both correct places for it).
