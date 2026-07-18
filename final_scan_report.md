# Final Scan Report — warehouse-app / warehouse-infra / warehouse-gitops

Scope: hardcoded-values scan, security scan, README staleness check across all three repos. Read-only investigation was done via parallel sub-agents per repo; fixes below were applied directly against the findings.

## 1. Hardcoded values

### Fixed

| Repo | File | What was wrong | Fix |
|---|---|---|---|
| warehouse-app | `backend/helm/values.yaml:168` | `FRONTEND_BASE_URL` hardcoded to a raw internal ELB hostname (`http://a255dbb8fadf...elb.amazonaws.com`) — this value feeds directly into QR-code generation (`backend/app.py`, `get_box_qr`) | Changed to `https://warehousems.online`. **Not a live-prod bug**: `warehouse-gitops/envs/production/backend-values.yaml` already overrides this correctly — this was only the chart's own stale default, used by a bare `helm install` without the gitops overlay |

### Already fixed in an earlier pass (verified still correct, not re-touched)

See `warehouse-app/hardcoded_findings.md` (pre-existing file from a prior scan) for the full list — confirmed accurate: `S3_REGION`/`BEDROCK_REGION`/`BEDROCK_MODEL_ID` are `os.environ.get(...)` with defaults, and `modules/eks/main.tf`'s backend S3 IAM policy now references `var.s3_bucket_name` instead of a duplicated literal.

### Reviewed, no fix needed (correct config layer for that value)

| Repo | Location | Why it's fine |
|---|---|---|
| warehouse-infra | `backend.tf:3,5`, `core/backend.tf:3,5` | Terraform backend blocks can't use variable interpolation — hard language limitation, already documented in README's "Known limitations" |
| warehouse-infra | `modules/iam/github_oidc.tf` (account ID, region, bucket name inline in the two inline policy JSON blocks) | Deliberate verbatim copies of the existing `warehouse-terraform-minimal`/`warehouse-s3-ssm-minimal` policy documents, for permission parity with the legacy IAM user — see Security section below |
| warehouse-gitops | `envs/production/*-values.yaml` (account ID, region, bucket name, domain, in-cluster service URLs) | This *is* the per-environment config surface for the Helm charts — single-environment repo by design, no templating/overlay layer exists to move these into. Not a bug, just the current (documented) design |

### Not found
No hardcoded passwords/API keys in plaintext anywhere across the three repos.

## 2. Security scan

### Fixed
- `warehouse-app`: removed 2 stray git-tracked `.DS_Store` files (`.DS_Store`, `frontend/.DS_Store`) — already covered by `.gitignore`, just predated the rule. Not a secret, just repo hygiene.

### Flagged, not auto-fixed (needs a human decision)

| Repo | Location | Finding | Why not auto-fixed |
|---|---|---|---|
| warehouse-app | `backend/app.py:429-434`, route `/uploads/<path:filename>` (`serve_upload`) | Unauthenticated file-read endpoint. Appears to be dead code — nothing in the current codebase writes to local `UPLOAD_FOLDER` anymore (`upload_to_s3` uploads straight to S3), so in practice this always 404s — but it's still a live, unauthenticated route. | Flagged for deliberate removal-or-keep decision rather than deleted unilaterally |
| warehouse-infra | `modules/iam/github_oidc.tf`, `Sid: TerraformIAM` in the `warehouse-terraform-minimal` inline policy | `Resource: "*"` combined with `iam:PassRole`, `iam:CreateRole`, `iam:PutRolePolicy` — broader than the OIDC build/push role actually needs (classic priv-esc shape) | Exact copy of the pre-existing production policy, copied intentionally for parity in an earlier task. Tightening it changes behavior shared with the legacy `warehouse-github-actions` user and needs a scoping decision, not a blind edit |
| warehouse-gitops | `envs/production/*-values.yaml` (all 5 services) | No `resources:` (CPU/memory requests/limits) block on any workload | Picking real limits without usage/profiling data risks OOM-kills or CPU throttling in production if guessed wrong — needs profiling, not invented numbers |

### Reviewed, no issue
- No secrets committed in plaintext anywhere (all three repos: env vars/secretKeyRefs only, `.env`/`.env.example` use placeholders, ESO pulls real values from AWS Secrets Manager).
- `warehouse-app` auth: all routes are `@jwt_required()` except `/health`, `/auth/register`, `/auth/login` (correct); passwords hashed via bcrypt; workspace-access checks (`_check_workspace_access`) applied consistently on data routes.
- `warehouse-gitops`: no plaintext `kind: Secret` manifests, no RBAC wildcards (no RBAC manifests exist at all), no `privileged`/root containers, image tags pinned to git SHAs (not `latest`).
- `warehouse-infra`: EKS public endpoint open to `0.0.0.0/0` — already documented as an accepted dev/demo-posture limitation in README. Public S3 bucket policy is tightly scoped to `s3:GetObject` only (intentional, public image bucket).
- No TODO/FIXME/XXX/HACK security comments found in any of the three repos.

## 3. README updates

| Repo | Section | Change |
|---|---|---|
| warehouse-app | `README.md` § CI/CD flow | Added a new "AWS auth: OIDC, not static keys" subsection describing the `role-to-assume` OIDC flow, the `warehouse-github-actions-oidc` role, its trust-policy scoping, and the required `AWS_OIDC_ROLE_ARN` secret. Updated the `build-service.yml` bullet to say OIDC instead of implying static creds |
| warehouse-infra | `README.md` § Module structure | Added a `modules/iam` row |
| warehouse-infra | `README.md` § IAM permissions | Added a full subsection documenting the OIDC provider, the `warehouse-github-actions-oidc` role, its trust conditions, the permission-parity approach (managed policy + inline-policy copies + by-reference customer-managed policy), and the known `iam:PassRole`-on-`*` scoping gap |
| warehouse-gitops | — | No changes. Verified line-by-line against actual repo state (ESO manifests, App-of-Apps structure, `envs/production/` contents) — already fully accurate, nothing stale found |

Not touched (already accurate, confirmed by scan): core/root two-layer split, External Secrets Operator docs, EKS public-endpoint known-limitation note. No `destroy.sh` exists in `warehouse-infra` — the README's `terraform destroy`-based teardown section is consistent with reality, so there was nothing to reconcile there.

## 4. Remaining issues needing manual attention

1. **`serve_upload` route** (`warehouse-app/backend/app.py:429`) — decide: delete (looks dead) or keep+gate. Not changed in this pass.
2. **`TerraformIAM` inline policy scope** (`warehouse-infra/modules/iam/github_oidc.tf`) — `iam:PassRole`/`iam:CreateRole`/`iam:PutRolePolicy` on `Resource: "*"` is broader than the OIDC CI role needs; scoping it down means diverging from parity with the legacy user's policy, which needs a product decision.
3. **Missing resource requests/limits** on all 5 `warehouse-gitops/envs/production/*-values.yaml` workloads — needs profiling real CPU/memory usage before setting values, not a blind default.
4. **Terraform state file** was noted sitting untracked (gitignored) in `warehouse-gitops` repo root during the scan — not a git-committed secret, but worth confirming it isn't accidentally left on a shared machine.
