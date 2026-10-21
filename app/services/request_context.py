"""Verified client address shared by SQL and security notifications."""
from ipaddress import ip_address, ip_network

from flask import has_request_context, request
from werkzeug.middleware.proxy_fix import ProxyFix


def client_ip() -> str:
    """Use the peer selected by the trusted-proxy middleware, never raw XFF."""
    if not has_request_context() or not request.remote_addr:
        return ''
    try:
        address = ip_address(request.remote_addr)
    except ValueError:
        return ''
    return str(address)


class TrustedProxyFix:
    """Apply forwarded headers only when the socket peer is explicitly trusted.

    The configured edge must append/overwrite forwarded headers. Selecting the
    configured number of hops from the right prevents a client-supplied prefix
    from becoming the audit identity.
    """

    def __init__(self, application, trusted_cidrs=(), forwarded_for_hops=1):
        if isinstance(trusted_cidrs, str):
            trusted_cidrs = [part.strip() for part in trusted_cidrs.split(',') if part.strip()]
        self.networks = tuple(ip_network(value, strict=False) for value in trusted_cidrs)
        hops = int(forwarded_for_hops)
        if hops < 0:
            raise ValueError('PROXY_X_FOR_HOPS debe ser cero o un entero positivo.')
        self.direct_application = application
        self.forwarded_application = ProxyFix(application, x_for=hops, x_proto=1, x_host=1)

    def __call__(self, environ, start_response):
        try:
            peer = ip_address(environ.get('REMOTE_ADDR', ''))
        except ValueError:
            peer = None
        if peer is not None and any(peer in network for network in self.networks):
            return self.forwarded_application(environ, start_response)
        return self.direct_application(environ, start_response)
