# The code checks: each one looks at one case and the Agent's reply, and says pass (True) or fail (False).
from collections.abc import Callable


def reply_not_empty(case: dict, reply: str) -> bool:
    # The Agent must say something (spaces alone do not count).
    return bool(reply.strip())


def contains_expected(case: dict, reply: str) -> bool:
    # The reply must contain the text the case expects. Upper/lower case does not matter.
    return case["expected_contains"].lower() in reply.lower()


# Name -> check function. The runner runs every check on every case.
CHECKS: dict[str, Callable[[dict, str], bool]] = {
    "reply_not_empty": reply_not_empty,
    "contains_expected": contains_expected,
}
