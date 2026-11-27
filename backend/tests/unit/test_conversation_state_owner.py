# Code guard (story 4.4, AD-10, AR-15): only inbox's named functions change a Conversation's
# state. This test reads the source code (it does not run it) and lists every place that
# writes something called "state". The list must be exactly the two named setters.
#
# Forms it catches: x.state = …, x.state += …, x.state: str = …, (a, x.state) = …,
# setattr(x, "state", …), Conversation(state=…), .values(state=…), and SQL text "SET state".
# Tests are not scanned: they set state by raw SQL on purpose.
# When bookings (Epic 5) gets its own state setters, add them to ALLOWED.
import ast
import re
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"
SERVICE = "app/modules/inbox/service.py"
ALLOWED = {(SERVICE, "start_handoff"), (SERVICE, "end_handoff")}
_SQL_SET_STATE = re.compile(r"SET\s+state\b", re.IGNORECASE)


def _targets(node: ast.AST) -> list[ast.AST]:
    """The things an assignment writes to, with tuple targets opened up."""
    if isinstance(node, ast.Assign):
        found = list(node.targets)
    elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
        found = [node.target]
    else:
        return []
    flat = []
    while found:
        target = found.pop()
        if isinstance(target, (ast.Tuple, ast.List)):
            found.extend(target.elts)
        else:
            flat.append(target)
    return flat


def _writes_state(node: ast.AST) -> bool:
    if any(isinstance(t, ast.Attribute) and t.attr == "state" for t in _targets(node)):
        return True
    if isinstance(node, ast.Call):
        func = node.func
        name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""
        if name == "setattr" and len(node.args) >= 2:
            key = node.args[1]
            if isinstance(key, ast.Constant) and key.value == "state":
                return True
        if name in {"Conversation", "values"} and any(k.arg == "state" for k in node.keywords):
            return True
    return isinstance(node, ast.Constant) and isinstance(node.value, str) and bool(_SQL_SET_STATE.search(node.value))


def _state_writers(path: Path) -> set[tuple[str, str]]:
    """(file, enclosing function) for every state write in one file."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    relative = path.relative_to(APP.parent).as_posix()
    found = set()

    def visit(node: ast.AST, function: str) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            function = node.name
        if _writes_state(node):
            found.add((relative, function))
        for child in ast.iter_child_nodes(node):
            visit(child, function)

    visit(tree, "<module>")
    return found


def test_only_named_functions_change_conversation_state():
    files = sorted(APP.rglob("*.py"))
    assert len(files) > 10  # the scan cannot pass by reading nothing
    writers = set().union(*(_state_writers(path) for path in files))
    assert writers == ALLOWED


def test_the_guard_catches_every_form():
    # The guard itself: each form below must be seen (else the test above could pass by mistake).
    forms = [
        "x.state = 'a'",
        "x.state += 'a'",
        "x.state: str = 'a'",
        "a, x.state = 1, 2",
        "setattr(x, 'state', 'a')",
        "Conversation(state='a')",
        "update(C).values(state='a')",
        "text('UPDATE conversations SET state = 1')",
    ]
    for source in forms:
        assert any(_writes_state(node) for node in ast.walk(ast.parse(source))), source
