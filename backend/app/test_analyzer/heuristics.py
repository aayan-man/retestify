import re


def naming_convention_match(test_name: str, component_name: str) -> float:
    """Confidence in [0, 1] that a test named `test_name` targets `component_name`,
    based on pytest/unittest naming conventions (test_<name>, Test<Name>.test_<name>)."""
    t = test_name
    if t.lower().startswith("test_"):
        t = t[5:]
    elif t.lower().startswith("test"):
        t = t[4:]

    c = component_name
    if not t or not c:
        return 0.0

    if t == c:
        return 0.9
    if t.lower() == c.lower():
        return 0.85

    tokens = {tok for tok in re.split(r"[_\s]+", t.lower()) if tok}
    if c.lower() in tokens:
        return 0.6
    if c.lower() in t.lower():
        return 0.4
    return 0.0
