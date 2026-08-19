import json


def bounded_json_string(value: str, rendered_limit: int) -> str:
    """JSON-encode the longest deterministic prefix within the rendered limit."""
    low, high, best = 0, len(value), json.dumps("")
    while low <= high:
        middle = (low + high) // 2
        candidate = json.dumps(value[:middle], ensure_ascii=False)
        if len(candidate) <= rendered_limit:
            best = candidate
            low = middle + 1
        else:
            high = middle - 1
    return best
