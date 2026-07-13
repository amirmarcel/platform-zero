# Local Setup

Clean laptop to a running platform, in order. Everything here runs on `kind` —
no cloud account, no Terraform apply.

## Prerequisites

- Docker Desktop (or another local Docker daemon)
- [`kind`](https://kind.sigs.k8s.io/), `kubectl`, `helm`
- Python 3.11+ (for `platformctl`)
- A fork of this repo, and `platform/config.yaml`'s `argocd.repo_url` pointed at it

```
pip install -e ".[dev]"
```

## 1. Publish the demo-api image

`services/demo-api/service.yaml` pins `image.tag: v0.1.0`. That tag has to
actually exist in your GHCR before ArgoCD can pull a running pod — otherwise
the pod sits in `ImagePullBackOff` forever. Publish it one of two ways:

- **Manual (fastest first run):** on GitHub, Actions → `demo-api-image` →
  Run workflow, on `main`.
- **Tag-triggered:** `git tag demo-api-v0.1.0 && git push origin demo-api-v0.1.0`
  — this publishes `ghcr.io/<you>/demo-api:v0.1.0` via
  `.github/workflows/demo-api-release.yaml`.

Then make the package public: GitHub → your profile → Packages → `demo-api` →
Package settings → Change visibility → Public. New GHCR packages are private
by default, and a local `kind` cluster has no pull credentials configured —
without this step, the pull fails even though the tag exists. (The
alternative is creating an `imagePullSecret` in the `demo-api` namespace and
wiring it into the chart, which is out of scope here — making the package
public is the one-line option for a demo.)

## 2. Bring up the cluster

```
make cluster-up
```

Creates the `kind` cluster (`local/kind-config.yaml`, ports 80/443 mapped to
the host) and installs `ingress-nginx`'s kind-specific manifest, waiting for
the controller pod to be ready.

## 3. Install the platform

```
make platform-install
```

Installs ArgoCD (`argocd` namespace) and kube-prometheus-stack (`monitoring`
namespace) via Helm, with the Grafana dashboard sidecar enabled.

## 4. Bootstrap GitOps

```
make platform-bootstrap
```

Applies `argocd/root-app.yaml` — the one and only `kubectl apply` in the
whole loop. From here, ArgoCD reads `argocd/apps/` from git and syncs
everything itself: the `demo-api` Application (rendered by `platformctl
render`) and the `observability` Application (the PrometheusRule/dashboard
wrapper chart).

`root-app.yaml`'s `repoURL` is a `__ARGOCD_REPO_URL__` placeholder,
substituted at apply time from `platform/config.yaml` — nothing on disk
changes. `argocd/apps/demo-api.yaml` and `argocd/apps/observability.yaml` are
generated artifacts with the real `repoURL` already baked in by
`platformctl render`, so make sure `platform/config.yaml` points at your fork
*before* rendering, and that the rendered files are committed and pushed —
ArgoCD reads them from the remote, not from your working tree.

## 5. Verify

ArgoCD synced both Applications without a manual `kubectl apply`:

```
kubectl get application -n argocd
```

Expect `demo-api` and `observability`, both `Synced`/`Healthy`.

The rendered Prometheus rules made it in as a real `PrometheusRule` CR:

```
kubectl get prometheusrule -n monitoring
```

Expect `demo-api`.

Confirm Prometheus is actually scraping demo-api under the `job` label the
recording rules and alerts key off of:

```
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090
```

Open http://localhost:9090/targets and confirm a target with `job="demo-api"`
and state `UP`. If it's missing, the `ServiceMonitor`
(`helm/service/templates/servicemonitor.yaml`) isn't being picked up — check
its `release` label matches the Helm release name used in step 3
(`kube-prometheus-stack` by default).

The dashboard landed as a ConfigMap the Grafana sidecar loads automatically:

```
kubectl get configmap -n monitoring -l grafana_dashboard=1
```

Expect `demo-api-dashboard`.

## Adding another service

From here on, shipping a new service is:

```
platformctl init <name> --owner <team> --tier <1|2|3>
$EDITOR services/<name>/service.yaml
platformctl render <name>
git add . && git commit -m "feat: add <name>"
git push
```

No `kubectl apply`, no hand-written Kubernetes manifest, no dashboard ticket.
ArgoCD picks up `argocd/apps/<name>.yaml` on its next sync.

## Tear down

```
make cluster-down
```
