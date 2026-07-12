# AGENTS.md

Read `docs/platform-philosophy.md` and `docs/service-contract.md` before any task.
They define this project's scope, principles, and the contract every service obeys.
These rules apply to all work in this repository.

## The deterministic spine

`services/<name>/service.yaml` is the **only** hand-written declaration of a service.

- Helm values, ArgoCD Applications, Prometheus rules, and Grafana dashboards are
  **generated** from it. Never hand-write or hand-edit a derived artifact.
- Rendering is **pure and deterministic**: the same manifest must always produce a
  byte-identical output. No timestamps, no random IDs, no map-ordering nondeterminism
  in generated files.
- If a derived artifact needs to change, change the manifest or change the renderer.
  Never patch the output.

## Hard rules

- **No LLM calls, no AI dependencies, anywhere in this project.** This is platform
  infrastructure. Every behavior is deterministic and testable.
- **No secrets in the repository.** No real credentials, tokens, ARNs, account IDs, or
  cluster endpoints — not in code, not in examples, not in test fixtures. Use obvious
  placeholders.
- **No cloud provisioning.** Terraform in this repo is validated and planned, never
  applied. Do not run `terraform apply`. Do not create AWS resources.
- **Everything runs locally.** The cluster is `kind`. If a task cannot be demonstrated
  on a laptop with no cloud account, it is out of scope.

## Validation and tests

- Every `platformctl validate` rule from the contract's enforcement table gets a unit
  test, including the failure case. A validator with no failing-input test is not a
  validator.
- Rendering gets golden-file tests: fixture manifest in, expected artifact out.
- CI runs: schema validation → render → `git diff --exit-code` on derived artifacts →
  unit tests. A drifted artifact fails the build.

## Scope guardrails

Out of scope. Do not build these, and do not suggest them:

- Multi-cluster, multi-region, or cluster federation
- Service mesh, custom operators, or CRDs
- Any dashboard/alerting backend beyond Prometheus + Grafana
- Authentication, authorization, or a web UI for the platform itself

If a task seems to require something on this list, stop and say so rather than
expanding scope.

## Repository hygiene

- This repository is a self-contained engineering project. It contains no references to
  companies, job descriptions, interviews, hiring, or the process by which it was built.
- Commits follow conventional prefixes: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`,
  `ci:`, `chore:`.
- Show each command before running it.
