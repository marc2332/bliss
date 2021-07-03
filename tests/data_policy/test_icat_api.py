import pytest
import base64
import xml.etree.ElementTree as etree
from bliss.icat.client.elogbook import IcatElogbookClient
from bliss.icat.client.metadata import IcatMetadataClient


@pytest.fixture
def elogbook(icat_logbook_server):
    port, messages = icat_logbook_server
    client = IcatElogbookClient(f"http://localhost:{port}")
    yield client, messages


@pytest.fixture
def icat_metadata(stomp_server, activemq_rest_server, icat_subscriber):
    _, jport = activemq_rest_server
    host, port = stomp_server
    messages = icat_subscriber
    client = IcatMetadataClient([f"{host}:{port}"], monitor_port=jport)
    yield client, messages


def test_elogbook_message_wrong_category(elogbook):
    client, messages = elogbook
    with pytest.raises(ValueError):
        client.send_message(
            "mycontent", "wrongcategory", "hg123", "id00", "datasetname"
        )
    assert messages.empty()


def test_elogbook_message(elogbook):
    client, messages = elogbook
    client.send_message("mycontent", "comment", "hg123", "id00", "datasetname")
    message = messages.get(timeout=10)
    message.pop("apikey")
    message.pop("creationDate")
    expected = {
        "type": "annotation",
        "datasetName": "datasetname",
        "category": "comment",
        "content": [{"format": "plainText", "text": "mycontent"}],
        "investigation": "hg123",
        "instrument": "id00",
    }
    assert message == expected
    assert messages.empty()


def test_elogbook_data(elogbook):
    client, messages = elogbook
    client.send_data(b"123", "application/octet-stream", "hg123", "id00")
    message = messages.get(timeout=10)
    message.pop("apikey")
    message.pop("creationDate")
    data = message.pop("base64")
    data = data.replace("data:application/octet-stream;base64,", "")
    assert base64.b64decode(data.encode()) == b"123"
    expected = {"investigation": "hg123", "instrument": "id00"}
    assert message == expected
    assert messages.empty()


def test_start_investigation(icat_metadata):
    client, messages = icat_metadata
    client.check_health()
    client.start_investigation(proposal="hg123", beamline="id00")
    message = messages.get(timeout=10)

    root = etree.fromstring(message)
    names = {child.tag.replace("{http://www.esrf.fr/icat}", "") for child in root}
    expected = {"startDate", "experiment", "instrument"}
    assert names == expected
    assert messages.empty()


def test_send_metadata(icat_metadata):
    client, messages = icat_metadata
    client.check_health()
    client.send_metadata(
        proposal="hg123",
        beamline="id00",
        collection="samplename",
        dataset="datasetname",
        path="/path-of-dataset",
        metadata={"field1": "value1", "field2": [1, 2, 3]},
    )
    message = messages.get(timeout=10)

    root = etree.fromstring(message)
    names = {child.tag.replace("{http://www.esrf.fr/icat}", "") for child in root}
    expected = {
        "endDate",
        "location",
        "startDate",
        "parameter",
        "sample",
        "investigation",
        "instrument",
        "name",
    }
    assert names == expected
    assert messages.empty()
