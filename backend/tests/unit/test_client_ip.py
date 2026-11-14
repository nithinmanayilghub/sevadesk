# Unit tests for client_ip (story 2.2, D5, AD-6). The proxy (Caddy or the AWS ALB) puts the
# real client IP at the END of X-Forwarded-For. Values before it may be written by the client.
from starlette.requests import Request

from app.core.client_ip import client_ip


def request(forwarded: str | None = None, client: tuple[str, int] | None = ("172.18.0.5", 5000)) -> Request:
    headers = [(b"x-forwarded-for", forwarded.encode())] if forwarded is not None else []
    return Request({"type": "http", "headers": headers, "client": client})


def test_rightmost_value_wins():
    # A client wrote "1.2.3.4" itself; the proxy appended the real one.
    assert client_ip(request("1.2.3.4, 10.0.0.9")) == "10.0.0.9"


def test_spaces_are_stripped():
    assert client_ip(request(" 10.0.0.9 ")) == "10.0.0.9"


def test_value_that_is_not_an_ip_falls_back_to_the_socket():
    assert client_ip(request("garbage")) == "172.18.0.5"


def test_no_header_uses_the_socket():
    assert client_ip(request()) == "172.18.0.5"


def test_no_header_and_no_client_is_unknown():
    assert client_ip(request(client=None)) == "unknown"


def test_ipv6_is_grouped_by_its_slash_64():
    # One home or phone gets a whole /64 block, so each address alone is easy to change.
    assert client_ip(request("2001:db8::1")) == "2001:db8::/64"
    assert client_ip(request("2001:db8::ffff")) == "2001:db8::/64"
