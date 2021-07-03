def expected_icat_mq_message(scan_saving, dataset=False):
    """Information expected to be received by ICAT message queue
    """
    url = "http://www.esrf.fr/icat"
    if dataset:
        start = f'<tns:dataset xmlns:tns="{url}" complete="true">'
        end = "</tns:dataset>"
        exptag = "investigation"
    else:
        start = f'<tns:investigation xmlns:tns="{url}">'
        end = "</tns:investigation>"
        exptag = "experiment"
    proposal = f"<tns:{exptag}>{scan_saving.proposal_name}</tns:{exptag}>"
    beamline = f"<tns:instrument>{scan_saving.beamline}</tns:instrument>"
    info = {"start": start, "end": end, "proposal": proposal, "beamline": beamline}
    if dataset:
        info["dataset"] = f"<tns:name>{scan_saving.dataset_name}</tns:name>"
        info[
            "sample"
        ] = f'<tns:sample xmlns:tns="{url}"><tns:name>{scan_saving.collection_name}</tns:name></tns:sample>'
        info["path"] = f"<tns:location>{scan_saving.icat_root_path}</tns:location>"
    return info


def assert_icat_received(icat_subscriber, expected_message, dataset=None, timeout=10):
    """Check whether ICAT received the correct information
    """
    print("\nWaiting for ICAT message ...")
    icat_received = icat_subscriber.get(timeout=timeout)
    print(f"Validating ICAT message: {icat_received}")
    for k, v in expected_message.items():
        if k == "start":
            assert icat_received.startswith(v), k
        elif k == "end":
            assert icat_received.endswith(v), k
        else:
            assert v in icat_received, k


def assert_icat_metadata_received(icat_subscriber, phrases, timeout=10):
    """Check whether ICAT received the correct information
    """
    print("\nWaiting for ICAT message ...")
    icat_received = icat_subscriber.get(timeout=timeout)
    if isinstance(phrases, str):
        phrases = [phrases]
    for phrase in phrases:
        assert phrase in icat_received


def assert_logbook_received(
    icat_logbook_subscriber,
    messages,
    timeout=10,
    complete=False,
    category=None,
    scan_saving=None,
):
    if not category:
        category = "comment"
    print("\nWaiting of ICAT logbook message ...")
    logbook_received = icat_logbook_subscriber.get(timeout=timeout)
    print(f"Validating ICAT logbook message: {logbook_received}")
    assert logbook_received["category"] == category

    if scan_saving is not None:
        assert logbook_received["investigation"] == scan_saving.proposal_name
        assert logbook_received["instrument"] == scan_saving.beamline
        # Due to the "atomic datasets" the server is always
        # STANDBY (no dataset name specified):
        assert logbook_received["datasetName"] is None
        # assert logbook_received["datasetName"] == scan_saving.dataset_name

    content = logbook_received["content"]
    if isinstance(messages, str):
        messages = [messages]
    for message, adict in zip(messages, content):
        if complete:
            assert adict["text"] == message
        else:
            assert message in adict["text"]


def assert_icat_received_current_proposal(scan_saving, icat_subscriber):
    assert_icat_received(icat_subscriber, expected_icat_mq_message(scan_saving))
