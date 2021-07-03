from bliss.config.static import get_config
from bliss.icat.client.main import IcatClient


def icat_client_from_config():
    kwargs = get_config().root.get("icat_servers")
    return IcatClient(**kwargs)
