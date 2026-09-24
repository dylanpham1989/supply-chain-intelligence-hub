# Deployment

Three ways to run this, in increasing order of how much it resembles
production and decreasing order of how much of it actually runs.

| | What runs it | Datastores | State |
|---|---|---|---|
| Compose | `make up` | containers | runs, used daily |
| Kubernetes on kind | `make kind-up && make kind-deploy` | containers in the cluster | runs, exercised in CI |
| AWS | Terraform in `infra/terraform` | RDS, ElastiCache, S3 | written, validated, scanned, never applied |

The last row is the honest one. It is explained at the bottom.

## Compose

```bash
make up          # api, worker, web, postgres, redis, minio
make migrate
make seed
make smoke       # upload a contract, wait for indexing, ask a question
```

## Kubernetes on kind

```bash
make kind-up      # cluster, ingress-nginx, metrics-server
make kind-deploy  # build, load, apply, migrate, seed
BASE_URL=http://localhost:8081 make smoke
make kind-down
```

`kind-up` installs two add-ons the manifests assume. Ingress is how anything
reaches the app. metrics-server is what the HPA reads: without it the HPA
reports `<unknown>` forever and never scales, which is the most common reason a
first HPA appears not to work.

Images are built locally and pushed into the node with `kind load`. The node has
its own container store, so an image on the host is not an image the kubelet can
see, and the overlay sets `imagePullPolicy: IfNotPresent` so nothing tries a
registry that does not exist.

### What the manifests say and why

**Probes.** Three of them, and they answer different questions. `startupProbe`
gives the api up to two minutes to load the embedding model; while it runs the
other two are suspended, which is what stops a slow start from being killed by
liveness in a loop that never ends. `livenessProbe` asks whether the process is
wedged, and its failure restarts the pod. `readinessProbe` asks whether the pod
can serve right now, and its failure only takes it out of the Service. Liveness
points at `/health/live`, which touches no dependency, so a slow database cannot
restart every pod at once.

**Rolling updates without dropped requests.** `maxUnavailable: 0` keeps the old
pod serving until the new one is ready. `preStop: sleep 5` covers the gap that
surprises people: Kubernetes sends SIGTERM and removes the Service endpoint at
the same time, and the two are not atomic, so traffic can still arrive for a few
hundred milliseconds after the process has been told to stop.

**Worker grace period.** 320 seconds, against an arq job timeout of 300. A
rollout that cut a job off in the middle would leave a document half indexed.
The two numbers are meant to be read together.

**Resources.** `requests` decide which node a pod is scheduled on; `limits`
decide when it gets throttled (cpu) or killed (memory). The worker holds torch
and the sentence-transformers model, about 1.2Gi resident, so its requests and
limits are both 2Gi: equal values put the pod in the Guaranteed QoS class, and a
node under memory pressure evicts something else first rather than losing a job
in flight. The numbers came from `kubectl top pods` after indexing real
documents, not from a guess.

**Migrations as a Job.** Not an init container. An init container runs once per
pod, so two api replicas start two `alembic upgrade head` at the same time and
race for the version table. The Job runs once and the rollout waits for it.

**Autoscaling.** The api scales on CPU at 70 percent, with a 30 second window
scaling out and 300 seconds scaling in, which is what keeps the replica count
from oscillating around the threshold.

The worker does not scale on CPU, and this is the interesting part. It spends
most of its time waiting on S3 and Postgres, so CPU stays low while the queue
backs up. The right signal is queue depth, which is what
`infra/k8s/base/worker-keda.yaml` scales on. KEDA is not installed in the demo
cluster, so that file is not part of any overlay; CI validates it against the
published CRD schema so it cannot rot.

**Security context.** Every pod runs as a non-root user with a read only root
filesystem, no privilege escalation and all capabilities dropped. A read only
root still needs somewhere to write, which is what the `/tmp` emptyDir is for:
document parsing writes a temporary file there. The web image is the
unprivileged nginx build, which listens on 8080 as uid 101.

**NetworkPolicy.** Kubernetes lets every pod talk to every other pod by default.
The policies here deny inbound traffic and then allow the four paths that are
actually used. They are applied but not enforced on kind, whose default CNI
ignores them; enforcement needs Calico or Cilium.

## AWS

`infra/terraform` describes the cloud version: VPC across two availability
zones, EKS with a managed node group in private subnets, RDS PostgreSQL 16,
ElastiCache Redis, an S3 bucket for documents, and an IAM role for the
application to assume.

### It is not applied

| Item | Roughly per month |
|---|---|
| EKS control plane | $73 |
| NAT gateway | $33 plus data |
| 2 x t3.large nodes | $120 |
| db.t4g.medium RDS | $50 |
| cache.t4g.micro | $12 |
| **Total** | **$290** |

That is a lot to leave running so that a link in a README works. So what runs in
CI is `terraform fmt`, `terraform validate`, `tflint` and `checkov`, and what
proves the Kubernetes design is the kind cluster with a smoke test.

`terraform plan` is not in CI either. A plan needs credentials for a real
account and refreshes real state; there is no account. validate and checkov are
the gate.

### The security decisions in there

**No access keys.** The application assumes an IAM role through the cluster's
OIDC provider (IRSA), so there is no key in a Secret to leak or rotate. The
trust policy pins both the service account and the audience; without the
audience condition, a token minted for something else would be accepted.

**Secrets.** A Kubernetes Secret is base64, not encryption: anyone who can run
`kubectl get secret -o yaml` can read it. The staging overlay does not contain
values, it contains an `ExternalSecret` that names an entry in AWS Secrets
Manager. The RDS master password is never in the code at all;
`manage_master_user_password` has RDS generate and store it.

**Network.** The database and cache accept traffic only from the node security
group, referenced by id rather than by CIDR, because a CIDR rule keeps working
when the subnet is reused for something else. Nodes are in private subnets. The
bucket blocks public access with all four flags and denies any request that is
not over TLS.

**Encryption.** One customer managed KMS key with rotation enabled covers the
bucket and the database, which an AWS managed key cannot be given.

### State

The backend is left local, with the S3 and DynamoDB configuration written out in
`backend.tf` as a comment. The lock table is the part that matters: without it,
two applies at the same time overwrite each other's state, and the recovery is
hand editing a JSON file that describes real infrastructure.

## CI

| Workflow | Jobs |
|---|---|
| `ci.yml` | backend lint, backend tests with Postgres, Redis and MinIO, frontend, API contract, manifest build |
| `security.yml` | assistant-trace audit, gitleaks, pip-audit, npm audit, trivy |
| `terraform.yml` | fmt, validate, tflint, checkov |

Two of these are worth calling out.

The **API contract** job regenerates `frontend/src/types/api.ts` from the
OpenAPI schema and fails if the result differs from what was committed. Renaming
a field in a Pydantic model without regenerating turns CI red instead of turning
the dashboard blank at runtime.

The **trace audit** runs `scripts/check_ai_traces.sh` over the full history on
every push. Keeping assistant tooling and attribution out of the repository is
then a property of the pipeline rather than of anyone remembering.

Tests need no API key: `LLM_PROVIDER=mock` makes the whole retrieval and
answering path run without a provider, which is what lets a public repository
have a green pipeline that anyone can fork and reproduce.
