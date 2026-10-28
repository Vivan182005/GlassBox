"""
Fetching pages whose address came from user input or a web search.

Company lookups fetch guessed careers pages (https://{name}.com/careers) and
search results, so a user can steer the server at any address. Without a check
that includes this machine's own services and private networks, directly or
through a redirect. safe_get only talks to public addresses on the standard
ports and re-checks every redirect hop.

The address is resolved here and again by requests when it connects, so a DNS
record that changes in between could still slip through; fixed vendor hosts
don't need this, only addresses a user or search result supplied.
"""

import ipaddress
import socket
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

MAX_REDIRECTS = 5


class UnsafeURL(ValueError):
    pass


def check_url(url: str) -> None:
    """Raises UnsafeURL unless url is http(s) on a standard port and every
    address its host resolves to is public."""
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise UnsafeURL("only http(s) URLs")
    if p.port not in (None, 80, 443):
        raise UnsafeURL("non-standard port")
    if p.username or p.password:
        raise UnsafeURL("credentials in URL")
    try:
        infos = socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == "https" else 80), proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise UnsafeURL("host does not resolve")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if not ip.is_global or ip.is_multicast:
            raise UnsafeURL("private or reserved address")


def safe_get(url: str, **kwargs: Any) -> requests.Response:
    """requests.get for untrusted addresses; redirects are followed by hand so
    each hop is checked."""
    kwargs.pop("allow_redirects", None)
    for _ in range(MAX_REDIRECTS + 1):
        check_url(url)
        r = requests.get(url, allow_redirects=False, **kwargs)
        if r.is_redirect and r.headers.get("location"):
            url = urljoin(url, r.headers["location"])
            continue
        return r
    raise UnsafeURL("too many redirects")
