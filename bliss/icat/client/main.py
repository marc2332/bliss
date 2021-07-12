from bliss.icat.client.elogbook import IcatElogbookClient
from bliss.icat.client.metadata import IcatMetadataClient
from bliss import current_session


class IcatClient:
    """Direct communication with ICAT: e-logbook and metadata
    """

    def __init__(
        self,
        metadata_urls: list,
        elogbook_url: str,
        elogbook_token: str = "elogbook-00000000-0000-0000-0000-000000000000",
        metadata_queue: str = "icatIngest",
        metadata_queue_monitor_port: int = None,
    ):
        self._elogbook = IcatElogbookClient(url=elogbook_url, api_key=elogbook_token)
        self._metadata = IcatMetadataClient(
            queue_urls=metadata_urls,
            queue_name=metadata_queue,
            monitor_port=metadata_queue_monitor_port,
        )

    def send_message(
        self,
        msg: str,
        msg_type="comment",
        proposal: str = None,
        beamline: str = None,
        dataset: str = None,
    ):
        if proposal is None:
            proposal = current_session.scan_saving.proposal_name
        if beamline is None:
            beamline = current_session.scan_saving.beamline
        if dataset is None:
            dataset = current_session.scan_saving.dataset_name
        self._elogbook.send_message(
            message=msg,
            category=msg_type,
            proposal=proposal,
            beamline=beamline,
            dataset=dataset,
        )

    def send_data(
        self,
        data: bytes,
        mimetype: str = None,
        proposal: str = None,
        beamline: str = None,
    ):
        if proposal is None:
            proposal = current_session.scan_saving.proposal_name
        if beamline is None:
            beamline = current_session.scan_saving.beamline
        self._elogbook.send_data(
            data, mimetype=mimetype, proposal=proposal, beamline=beamline
        )

    def send_text_file(
        self,
        filename: str,
        proposal: str = None,
        beamline: str = None,
        dataset: str = None,
    ):
        if proposal is None:
            proposal = current_session.scan_saving.proposal_name
        if beamline is None:
            beamline = current_session.scan_saving.beamline
        if dataset is None:
            dataset = current_session.scan_saving.dataset_name
        self._elogbook.send_text_file(
            filename, proposal=proposal, beamline=beamline, dataset=dataset
        )

    def send_binary_file(
        self, filename: str, proposal: str = None, beamline: str = None
    ):
        if proposal is None:
            proposal = current_session.scan_saving.proposal_name
        if beamline is None:
            beamline = current_session.scan_saving.beamline
        self._elogbook.send_binary_file(filename, proposal=proposal, beamline=beamline)

    def start_investigation(
        self, proposal: str = None, beamline: str = None, start_datetime=None
    ):
        if proposal is None:
            proposal = current_session.scan_saving.proposal_name
        if beamline is None:
            beamline = current_session.scan_saving.beamline
        self._metadata.start_investigation(
            proposal=proposal, beamline=beamline, start_datetime=start_datetime
        )

    def store_dataset(
        self,
        proposal: str = None,
        beamline: str = None,
        collection: str = None,
        dataset: str = None,
        path: str = None,
        metadata: dict = None,
        start_datetime=None,
        end_datetime=None,
    ):
        if proposal is None:
            proposal = current_session.scan_saving.proposal_name
        if beamline is None:
            beamline = current_session.scan_saving.beamline
        if collection is None:
            collection = current_session.scan_saving.collection
        if dataset is None:
            dataset = current_session.scan_saving.dataset_name
        if path is None:
            path = current_session.scan_saving.icat_root_path
        if metadata is None:
            metadata = current_session.scan_saving.dataset.get_current_icat_metadata()
        self._metadata.send_metadata(
            proposal=proposal,
            beamline=beamline,
            collection=collection,
            dataset=dataset,
            path=path,
            metadata=metadata,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
        )

    def ping(self, *args, **kw):
        """For compatibility with IcatTangoProxy
        """
        pass
