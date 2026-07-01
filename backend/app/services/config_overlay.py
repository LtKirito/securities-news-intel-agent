PROTECTED_KEYS = {
    "no_investment_advice",
    "public_sources_only",
    "source_required",
    "p0_sparse",
    "url_safety_required",
}


def deep_merge(base: dict, overlay: dict) -> dict:
    result = dict(base)
    for key, value in overlay.items():
        if key in PROTECTED_KEYS:
            continue
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result
