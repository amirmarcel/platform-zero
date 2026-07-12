from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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


class Runtime(BaseModel):
    model_config = ConfigDict(extra="forbid")

    port: int = Field(gt=0, le=65535)
    replicas: int = Field(ge=1)
    resources: Resources
    probes: Probes


class Image(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repository: str = Field(min_length=1)
    tag: str = Field(min_length=1)


class Slo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    availability: float = Field(gt=0, le=100)
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
    name: str = Field(min_length=1)
    owner: str = Field(min_length=1)
    tier: Literal[1, 2, 3]
    image: Image
    runtime: Runtime
    slo: Slo
    operations: Operations
