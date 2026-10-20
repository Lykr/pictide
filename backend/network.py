"""System HTTP(S) proxies for external traffic; local services stay direct."""
from ipaddress import ip_address
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, build_opener, getproxies, proxy_bypass


def proxy_for_url(url):
    parts = urlsplit(str(url))
    host = (parts.hostname or '').lower().rstrip('.')
    if not host or host == 'localhost' or host.endswith(('.localhost', '.local', '.lan')):
        return None
    try:
        address = ip_address(host)
    except ValueError:
        if '.' not in host:  # Single-label names are normally local machines.
            return None
    else:
        if not address.is_global:
            return None
    if proxy_bypass(parts.netloc):
        return None
    scheme = {'ws': 'http', 'wss': 'https'}.get(parts.scheme, parts.scheme)
    proxy = getproxies().get(scheme)
    if proxy and '://' not in proxy:
        proxy = 'http://' + proxy
    return proxy


class _SystemProxyHandler(ProxyHandler):
    def __init__(self):
        super().__init__({})

    def http_open(self, request):
        # A redirect may leave a previous proxy's header on the new request.
        request.remove_header('Proxy-authorization')
        proxy = proxy_for_url(request.full_url)
        if proxy:
            return self.proxy_open(request, proxy, request.type)

    https_open = http_open


def open_url(request, *, timeout):
    # Redirects create a new request and run this handler for the new host too.
    return build_opener(_SystemProxyHandler()).open(request, timeout=timeout)
