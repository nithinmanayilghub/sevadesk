
from evals.checks import reply_is_short


def test_reply_is_short():
    assert reply_is_short({},"Namaste!") == True
    assert reply_is_short({},"a"*201) == False

