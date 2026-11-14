# The client's IP address, for rate limits (story 2.2, D5, AD-6).
#
# Requests reach the backend only through one proxy: Caddy (local, demo) or the AWS ALB.
# The proxy writes the real client IP as the LAST value of X-Forwarded-For.
# Caddy replaces any header the client sent; the ALB appends to it. Either way the
# rightmost value comes from the proxy, and values before it may be fake.
import ipaddress

from starlette.requests import Request


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    values = [value.strip() for value in forwarded.split(",") if value.strip()]
    if values:
        try:
            ip = ipaddress.ip_address(values[-1])
        except ValueError:
            ip = None  # not an IP: ignore the header
        if ip is not None:
            # "::ffff:1.2.3.4" is an IPv4 address in an IPv6 wrapper. Unwrap it first, or
            # every such client falls into the same block "::/64" and shares one limit.
            if ip.version == 6 and ip.ipv4_mapped:
                ip = ip.ipv4_mapped
            if ip.version == 6:
                # One home or phone gets a whole /64 block of IPv6 addresses, so we count
                # the block, not the single address.
                return str(ipaddress.ip_network(f"{ip}/64", strict=False))
            return str(ip)
    # No proxy header (tests, direct calls): use the socket's address.
    return request.client.host if request.client else "unknown"
