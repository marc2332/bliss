from bliss.controllers.transfocator import Transfocator


def test_transfocator(default_session, transfocator_mockup):

    """
    # getting mockup port (as is randomly chosen)
    host, port = wago_mockup.host, wago_mockup.port

    # patching port into config
    default_session.config.get_config("wago_simulator")["modbustcp"]["url"] = f"{host}:{port}"
    """
    transfocator = default_session.config.get("transfocator_simulator")
    transfocator.connect()
    # only reading is possible due to simulator limitations
    transfocator.status_read()
    transfocator.status_dict()