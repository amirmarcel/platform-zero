# Platform Philosophy

This repository models the first internal developer platform I would build for a
20–50 engineer company: the platform you stand up *before* you have a platform team.

At that size, the failure mode is not a lack of technology. It's that every service
is deployed a slightly different way, half of them have no owner, none of them have
a documented rollback, and the only person who knows how any of it works is the
engineer who wrote it. Adding Kubernetes to that situation does not fix it. Adding a
*contract* to it does.

## Principles

**1. One manifest per service. Everything else is derived.**
A service is declared once, in `service.yaml`. Its Helm values, its ArgoCD
Application, its Prometheus alert rules, and its Grafana dashboard are all generated
from that declaration. Engineers do not hand-write Kubernetes manifests, and the
platform does not trust hand-edits: CI regenerates every derived artifact and fails
the build if it drifts from the manifest.

**2. Every deployment is a git commit.**
There is no `kubectl apply` path to production. The cluster reconciles to what is in
the repository. This means a deploy is reviewable, a rollback is a revert, and the
question "what is actually running?" has a single answer that lives in git history.

**3. Standards are enforced, not documented.**
Resource limits, probes, an owner, an SLO, a runbook, a rollback strategy — these are
required fields, checked in CI, not bullet points in a wiki that nobody reads.
A standard that isn't enforced is a preference.

**4. Observability is provisioned, not requested.**
A new service gets a dashboard and an SLO alert on its first deploy, because both are
generated from the manifest. Nobody has to file a ticket to be monitored. The default
state of a service is "observable."

**5. Every alert points to a runbook, and every incident ends in a postmortem.**
An alert that fires at 3am and tells you nothing about what to do is a liability.
An alert links to a runbook. An incident produces a written timeline, a root cause,
and action items — and the action items land in the repo.

**6. The platform's customer is the engineer.**
The platform is an internal product, not a pile of infrastructure. It is judged by
whether a developer can ship a new service in an afternoon without learning
Kubernetes. That is the whole job.

## Non-goals

Stating what this platform deliberately does *not* do is as important as what it does.
At 20–50 engineers, most platform complexity is premature.

- **No multi-cluster or multi-region topology.** One cluster per environment. The
  organization does not have the operational headcount to run a fleet, and pretending
  otherwise buys complexity it cannot staff.
- **No service mesh.** The problems a mesh solves (mTLS everywhere, fine-grained
  traffic shifting, per-hop observability) are real at 300 services and speculative at
  15. Revisit when the pain is measurable.
- **No custom Kubernetes operators or CRDs.** Every CRD is a thing that must be
  versioned, upgraded, and explained to a new hire. The golden path is Helm plus
  generated manifests until that demonstrably fails.
- **No self-hosted control plane components that a managed service already provides.**
  Time spent operating a database is time not spent on developer experience.
- **No "platform as a gatekeeper."** The platform paves a road. It does not sit in the
  approval path of every change. If the golden path is slower than going around it,
  engineers will go around it, and they will be right to.

## Scope of this repository

**Running locally, for real:**
Kubernetes (kind), ArgoCD, Helm, Prometheus, Grafana, GitHub Actions, and the
`platformctl` CLI. The GitOps loop, the SLO alert, the failure injection, and the
rollback all genuinely execute.

**Represented as reference infrastructure, not provisioned:**
Terraform for VPC, IAM, EKS, and RDS. These modules are validated and planned in CI
but are not applied. They exist to show the production topology this platform is
designed to sit on, without claiming cloud infrastructure that was never stood up.

This split is deliberate and stated up front. The engineering that matters here is the
contract, the golden path, and the operational loop — none of which require a running
cloud account to demonstrate honestly.
