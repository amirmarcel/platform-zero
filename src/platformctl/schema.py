from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# RFC 1123 label grammar, reused by cli.py's `init` so a bad name is rejected
# before anything is written, not just at schema-validation time.
NAME_PATTERN = r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$"
NAME_MAX_LENGTH = 53


class ResourceSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cpu: str = Field(min_length=1)
    memory: str = Field(min_length=1)


class Resources(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requests: ResourceSpec
    limits: ResourceSpec


class Probes(BaseModel):
    model_config = ConfigDict(extra="forbid")

    readiness: str = Field(min_length=1)
    liveness: str = Field(min_length=1)


class EnvVar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    value: str


class Runtime(BaseModel):
    model_config = ConfigDict(extra="forbid")

    port: int = Field(gt=0, le=65535)
    replicas: int = Field(ge=1)
    resources: Resources
    probes: Probes
    env: list[EnvVar]


class Image(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repository: str = Field(min_length=1)
    tag: str = Field(min_length=1)


class Slo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    availability: float = Field(gt=0, lt=100)
    latency_p99_ms: int = Field(gt=0)
    window: str = Field(min_length=1)


class Operations(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runbook: str = Field(min_length=1)
    rollback: Literal["gitops-revert"]


class ServiceManifest(BaseModel):
    """services/<name>/service.yaml — see docs/service-contract.md.

    Every field is required in v1. There are no optional fields: an unset
    field is how a service ends up with no owner at 3am.
    """

    model_config = ConfigDict(extra="forbid")

    apiVersion: Literal["platform/v1"]
    # `name` becomes cluster *identity*: the ArgoCD Application name, the
    # destination namespace, the Helm release name, and the
    # Deployment/Service/ServiceMonitor/PrometheusRule/ConfigMap names. An
    # identity value that fails validation must be rejected, not sanitized —
    # sanitizing would break the manifest<->cluster name mapping. RFC 1123
    # label grammar, and <=53 chars (Helm's release-name limit, which is
    # stricter than Kubernetes' own 63-char limit).
    #
    # render.py's `_metric_name`/`_alert_name` still sanitize `name` for use
    # inside Prometheus metric/alert identifiers — that's a reference
    # context (a string embedded in another identifier), not an identity
    # one, so sanitizing there remains correct.
    name: str = Field(pattern=NAME_PATTERN, max_length=NAME_MAX_LENGTH)
    owner: str = Field(min_length=1)
    tier: Literal[1, 2, 3]
    image: Image
    runtime: Runtime
    slo: Slo
    operations: Operations
