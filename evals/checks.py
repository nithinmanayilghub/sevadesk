# The code checks: each one looks at one case and the Agent's reply, and says pass (True) or fail (False).
from collections.abc import Callable

MAX_REPLY_CHARS = 200 # chat customers want short answers   
def reply_not_empty(case: dict, reply: str) -> bool:
    # The Agent must say something (spaces alone do not count).
    return bool(reply.strip())


def contains_expected(case: dict, reply: str) -> bool:
    # The reply must contain the text the case expects. Upper/lower case does not matter.
    return case["expected_contains"].lower() in reply.lower()

def reply_is_short(case: dict,reply: str)-> bool:
    return len(reply) <= MAX_REPLY_CHARS
    

# Name -> check function. The runner runs every check on every case.
CHECKS: dict[str, Callable[[dict, str], bool]] = {
    "reply_not_empty": reply_not_empty,
    "contains_expected": contains_expected,
    "reply_is_short":reply_is_short
}

