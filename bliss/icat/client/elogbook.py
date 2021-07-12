from enum import Enum
from datetime import datetime
import requests
import logging
import base64
import mimetypes
import socket
from bliss.icat.client.url import normalize_url
from bliss import __version__

logger = logging.getLogger(__name__)

MessageCategory = Enum("MessageCategory", "debug info error commandLine comment")
MessageType = Enum("MessageType", "annotation notification")

MessageCategoryMapping = {
    "debug": MessageCategory.debug,
    "info": MessageCategory.info,
    "warning": MessageCategory.error,
    "warn": MessageCategory.error,
    "error": MessageCategory.error,
    "critical": MessageCategory.error,
    "fatal": MessageCategory.error,
    "command": MessageCategory.commandLine,
    "comment": MessageCategory.comment,
}

MessageTypeMapping = {
    MessageCategory.debug: MessageType.notification,
    MessageCategory.info: MessageType.notification,
    MessageCategory.error: MessageType.notification,
    MessageCategory.commandLine: MessageType.notification,
    MessageCategory.comment: MessageType.annotation,
}


class IcatElogbookClient:
    """Client for the e-logbook part of the ICAT+ REST API.

    REST API docs:
    https://icatplus.esrf.fr/api-docs/

    The ICAT+ server project:
    https://gitlab.esrf.fr/icat/icat-plus/-/blob/master/README.md
    """

    DEFAULT_SCHEME = "https"

    def __init__(
        self, url: str, api_key: str = "elogbook-00000000-0000-0000-0000-000000000000"
    ):
        url = normalize_url(url, default_scheme=self.DEFAULT_SCHEME)
        self._message_url = f"{url}/logbook/{api_key}/investigation/name/{{proposal}}/instrument/name/{{beamline}}/event"
        self._data_url = f"{url}/logbook/{api_key}/investigation/name/{{proposal}}/instrument/name/{{beamline}}/event/createFrombase64"
        self._client_id = {
            "machine": socket.getfqdn(),
            "software": "Bliss_v" + __version__,
        }
        self.timeout = 0.5

    def _add_default_payload(self, payload):
        payload.update(self._client_id)
        payload["creationDate"] = datetime.now().isoformat()

    def send_message(
        self, message: str, category: str, proposal: str, beamline: str, dataset: str
    ):
        url = self._message_url.format(proposal=proposal, beamline=beamline)
        payload = self.encode_message(message, category, dataset)
        self._add_default_payload(payload)
        requests.post(url, json=payload, timeout=self.timeout)

    def send_text_file(self, filename: str, proposal: str, beamline: str, dataset: str):
        with open(filename, "r") as f:
            message = f.read()
        self.send_message(
            message,
            category="comment",
            proposal=proposal,
            beamline=beamline,
            dataset=dataset,
        )

    def send_data(self, data: bytes, mimetype: str, proposal: str, beamline: str):
        url = self._data_url.format(proposal=proposal, beamline=beamline)
        payload = self.encode_mime_data(data, mimetype)
        self._add_default_payload(payload)
        requests.post(url, json=payload, timeout=self.timeout)

    def send_binary_file(self, filename: str, proposal: str, beamline: str):
        with open(filename, "rb") as f:
            data = f.read()
        mimetype, _ = mimetypes.guess_type(filename, strict=True)
        self.send_data(data, mimetype=mimetype, proposal=proposal, beamline=beamline)

    @staticmethod
    def encode_mime_data(data: bytes, mimetype: str) -> str:
        if not mimetype:
            # arbitrary binary data
            mimetype = "application/octet-stream"
        data_header = f"data:{mimetype};base64,"
        data_blob = base64.b64encode(data).decode("latin-1")
        return {"base64": data_header + data_blob}

    @staticmethod
    def encode_message(message: str, category: str, dataset: str) -> str:
        try:
            category = MessageCategoryMapping[category.lower()]
        except KeyError:
            raise ValueError(category, "Not a valid e-logbook category") from None
        message_type = MessageTypeMapping[category]
        return {
            "type": message_type.name,
            "datasetName": dataset,
            "category": category.name,
            "content": [{"format": "plainText", "text": message}],
        }
