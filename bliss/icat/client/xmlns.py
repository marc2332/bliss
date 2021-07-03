from datetime import datetime
import xml.etree.ElementTree as etree

ICAT_NAMESPACE_URL = "http://www.esrf.fr/icat"

etree.register_namespace("tns", ICAT_NAMESPACE_URL)


def root_node(name: str, **kw):
    return etree.Element(f"{{{ICAT_NAMESPACE_URL}}}{name}", **kw)


def child_node(parent, name: str, **kw):
    return etree.SubElement(parent, f"{{{ICAT_NAMESPACE_URL}}}{name}", **kw)


def encode_node_data(data) -> str:
    if isinstance(data, str):
        return data
    elif isinstance(data, (list, tuple)):
        return " ".join(list(map(str, data)))
    elif isinstance(data, bytes):
        return data.encode()
    elif isinstance(data, datetime):
        return data.isoformat()
    else:
        return str(data)


def data_node(parent, name: str, data, **kw):
    node = child_node(parent, name, **kw)
    node.text = encode_node_data(data)


def parameter_node(parent, name: str, value, **kw):
    node = child_node(parent, "parameter", **kw)
    data_node(node, "name", name)
    data_node(node, "value", value)


def dataset_as_xml(
    proposal: str,
    beamline: str,
    collection: str,
    dataset: str,
    path: str,
    metadata: dict = None,
    start_datetime=None,
    end_datetime=None,
):
    root = root_node("dataset", attrib={"complete": "true"})

    data_node(root, "investigation", proposal)
    data_node(root, "instrument", beamline)
    sample = child_node(root, "sample")
    data_node(sample, "name", collection)
    data_node(root, "name", dataset)
    data_node(root, "location", path)

    if start_datetime is None:
        start_datetime = datetime.now()
    data_node(root, "startDate", start_datetime)
    if end_datetime is None:
        end_datetime = datetime.now()
    data_node(root, "endDate", end_datetime)

    if metadata is not None:
        for name, value in metadata.items():
            parameter_node(root, name, value)

    return root


def investigation_as_xml(proposal: str, beamline: str, start_datetime=None):
    root = root_node("investigation")
    data_node(root, "experiment", proposal)
    data_node(root, "instrument", beamline)
    if start_datetime is None:
        start_datetime = datetime.now()
    data_node(root, "startDate", start_datetime)
    return root
