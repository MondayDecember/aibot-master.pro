"""Device-selection helper for the imagegen pool.

Kept free of torch/diffusers imports so it can be unit-tested without the
heavy GPU stack installed (app.py imports torch at module load).
"""


def parse_devices(env: str, count: int) -> list:
    """Resolve the IMAGEGEN_DEVICES setting into a list of device indices.

    - ""      -> [0]                (single card, default / back-compat)
    - "all"   -> every detected device
    - "0,1"   -> those indices, ignoring blanks and out-of-range values
    Always returns at least [0] so the service never ends up with no device.
    """
    env = (env or "").strip().lower()
    if env == "all":
        return list(range(count)) or [0]
    if env:
        picked = []
        for part in env.split(","):
            part = part.strip()
            if part.isdigit() and 0 <= int(part) < count and int(part) not in picked:
                picked.append(int(part))
        return picked or [0]
    return [0]
