CLUSTER_NAME := platform-zero
KIND_CONFIG  := local/kind-config.yaml
ARGOCD_NAMESPACE := argocd
MONITORING_NAMESPACE := monitoring
INGRESS_NGINX_MANIFEST := https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml

.PHONY: cluster-up platform-install platform-bootstrap cluster-down

## cluster-up: create the kind cluster and install ingress-nginx (kind provider).
cluster-up:
	kind create cluster --name $(CLUSTER_NAME) --config $(KIND_CONFIG)
	kubectl apply -f $(INGRESS_NGINX_MANIFEST)
	kubectl wait --namespace ingress-nginx \
		--for=condition=ready pod \
		--selector=app.kubernetes.io/component=controller \
		--timeout=180s

## platform-install: install ArgoCD and kube-prometheus-stack via Helm.
platform-install:
	helm repo add argo https://argoproj.github.io/argo-helm
	helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
	helm repo update
	helm upgrade --install argocd argo/argo-cd \
		--namespace $(ARGOCD_NAMESPACE) --create-namespace \
		--wait
	helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
		--namespace $(MONITORING_NAMESPACE) --create-namespace \
		--set grafana.sidecar.dashboards.enabled=true \
		--set grafana.sidecar.dashboards.label=grafana_dashboard \
		--wait

## platform-bootstrap: apply the root app-of-apps. This is the only kubectl
## apply in the loop — everything under argocd/apps/ (including
## observability.yaml, a derived artifact of `platformctl render`) is synced
## by ArgoCD from git from here on. root-app.yaml is hand-written and carries
## a __ARGOCD_REPO_URL__ placeholder, substituted here from
## platform/config.yaml; nothing on disk is modified.
platform-bootstrap:
	@REPO_URL=$$(grep -A1 '^argocd:' platform/config.yaml | grep 'repo_url:' | sed 's/.*repo_url:[[:space:]]*//'); \
	test -n "$$REPO_URL" || { echo "error: argocd.repo_url not found in platform/config.yaml"; exit 1; }; \
	sed "s|__ARGOCD_REPO_URL__|$$REPO_URL|g" argocd/root-app.yaml | kubectl apply -f -
## cluster-down: tear down the kind cluster.

cluster-down:
	kind delete cluster --name $(CLUSTER_NAME)
