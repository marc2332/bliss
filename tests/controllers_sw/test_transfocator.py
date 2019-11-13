from bliss.controllers.transfocator import Transfocator


def test_transfocator(default_session, transfocator_mockup):
    transfocator = default_session.config.get("transfocator_simulator")
    transfocator.connect()
    # only reading is possible due to simulator limitations
    transfocator.status_read()
    transfocator.status_dict()
