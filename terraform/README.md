# terraform/

This is reference infrastructure-as-code, not a deployed environment.

It shows the production topology this platform is designed to sit on — a
VPC, an EKS cluster, the IAM roles EKS needs, and an RDS database — as
modules under `modules/`, wired together in the root module (`main.tf`).
CI runs `terraform fmt -check` and `terraform validate` against it on every
push. **Nothing here is ever applied.** There is no `terraform plan` or
`terraform apply` step in CI, no backend configured, and no AWS credentials
available to this repository.

## Why validated but not applied

`docs/platform-philosophy.md` draws a deliberate line: the golden path, the
GitOps loop, the SLO alert, and the rollback all run for real on a local
`kind` cluster, because that's the engineering this repository exists to
demonstrate honestly. A cloud account is not part of that — standing one up
just to keep an EKS cluster running would misrepresent what's actually
being tested here, and would cost money for infrastructure nobody uses.

Keeping the Terraform layer validated (not just present) means it still has
to be internally consistent — the module graph has to type-check, every
required variable has to be wired, every resource block has to be
syntactically and semantically valid HCL for the `aws` provider. That's a
real, checked claim about the topology. "It plans cleanly against a real
account" is not a claim this repository makes.

## What's here

| Module | Represents |
|---|---|
| `modules/vpc` | VPC, public/private subnets across AZs, IGW, one NAT gateway, route tables |
| `modules/iam` | EKS cluster role and node role, with AWS-managed policy attachments |
| `modules/eks` | EKS cluster spanning both subnet tiers, one managed node group in the private subnets, a node security group |
| `modules/rds` | A single PostgreSQL instance in the private subnets, reachable only from the node security group |

This is a reference topology, not a production module library: one NAT
gateway (not one per AZ), one RDS instance (not Multi-AZ), one node group.
A real production rollout would tune those for the availability it needs;
this layer exists to show the shape of the topology, not to be a template
you `terraform apply` as-is.

## No secrets, no real identifiers

Every account ID, ARN, and endpoint you'd see in a real plan is either a
Terraform-computed attribute (unknown until apply, which never happens
here) or a placeholder variable default (region, CIDR blocks, instance
sizes). The only literal ARNs in this layer are AWS's own managed policy
ARNs (`arn:aws:iam::aws:policy/...`) — fixed, account-less identifiers
published by AWS for every account, not resources belonging to any
specific one. The RDS module uses `manage_master_user_password = true`
(RDS-managed credentials in Secrets Manager) instead of a `password` field,
so no credential of any kind is set here or persisted in this repository.

## Running it locally

```
cd terraform
terraform init -backend=false
terraform fmt -check -recursive
terraform validate
```

`-backend=false` is enough for `validate` — no state, no credentials, no
network calls beyond downloading the `aws` provider plugin.
