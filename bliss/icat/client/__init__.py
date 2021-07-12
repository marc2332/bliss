"""Currently two ICAT clients exist with the same API:

 1. `bliss.icat.client.IcatClient`: communicates directly with ICAT
 2. `bliss.icat.client.IcatTangoProxy`: communicates through tango servers

`IcatClient` is used when configured in the beacon configuration

    icat_servers:
        metadata_urls: [URL1, URL2]
        elogbook_url: URL3
        elogbook_token: elogbook-00000000-0000-0000-0000-000000000000

The default URL prefix is "tcp://" for the metadata and "https://"
for the e-logbook.

When not configured BLISS will fall back to `IcatTangoProxy` which
requires two TANGO devices with names "id00/metaexp/session_name"
and "id00/metadata/session_name". The configuration is done in the
TANGO device class properties.
"""

from .main import IcatClient  # noqa: F401
from .tango import IcatTangoProxy  # noqa: F401
from .config import icat_client_from_config  # noqa: F401
