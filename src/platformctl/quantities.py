"""Kubernetes-style resource quantity parsing (cpu cores, memory bytes)."""

MEMORY_UNITS = {
    "Ki": 1024,
    "Mi": 1024**2,
    "Gi": 1024**3,
    "Ti": 1024**4,
    "K": 1000,
    "M": 1000**2,
    "G": 1000**3,
}


def parse_cpu(quantity: str) -> float:
    """Parse a cpu quantity (e.g. '500m', '1') into cores."""
    quantity = quantity.strip()
    if quantity.endswith("m"):
        return float(quantity[:-1]) / 1000
    return float(quantity)


def parse_memory(quantity: str) -> float:
    """Parse a memory quantity (e.g. '512Mi', '1Gi') into bytes."""
    quantity = quantity.strip()
    for suffix in sorted(MEMORY_UNITS, key=len, reverse=True):
        if quantity.endswith(suffix):
            return float(quantity[: -len(suffix)]) * MEMORY_UNITS[suffix]
    return float(quantity)
