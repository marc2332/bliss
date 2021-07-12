from urllib.parse import urlparse


def normalize_url(
    url: str,
    default_scheme: str = None,
    default_port: int = None,
    absolute: bool = True,
) -> str:
    if not url:
        raise ValueError("URL is missing")
    if absolute and "//" not in url:
        url = "//" + url
    result = urlparse(url)
    scheme, netloc, *others = result
    if not netloc:
        raise ValueError(url, "URL is missing a network location")
    if not scheme and default_scheme:
        scheme = default_scheme
    if default_port and not result.port:
        netloc = f"{result.hostname}:{default_port}"
    newurl = type(result)(scheme, netloc, *others)
    return newurl.geturl()
