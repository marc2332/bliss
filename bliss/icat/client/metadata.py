import xml.etree.ElementTree as etree

from bliss.icat.client.xmlns import dataset_as_xml
from bliss.icat.client.xmlns import investigation_as_xml
from bliss.icat.client.messaging import IcatMessagingClient


class IcatMetadataClient:
    """Client for storing dataset metadata in ICAT.
    """

    def __init__(
        self, queue_urls: list, queue_name: str = "icatIngest", monitor_port: int = None
    ):
        self._client = IcatMessagingClient(
            queue_urls, queue_name, monitor_port=monitor_port
        )

    def send_metadata(
        self,
        proposal: str,
        beamline: str,
        collection: str,
        dataset: str,
        path: str,
        metadata: dict,
        start_datetime=None,
        end_datetime=None,
    ):
        root = dataset_as_xml(
            proposal=proposal,
            beamline=beamline,
            collection=collection,
            dataset=dataset,
            path=path,
            metadata=metadata,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
        )
        self._client.send(etree.tostring(root))

    def start_investigation(self, proposal: str, beamline: str, start_datetime=None):
        root = investigation_as_xml(
            proposal=proposal, beamline=beamline, start_datetime=start_datetime
        )
        self._client.send(etree.tostring(root))

    def check_health(self):
        """Raises an exception when not healthy
        """
        self._client.check_health()
