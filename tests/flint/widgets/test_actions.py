"""Testing image plot."""

import base64

from silx.gui.plot import PlotWindow
from bliss.flint.model import flint_model
from bliss.flint.manager.manager import ManageMainBehaviours
from bliss.flint.widgets.utils import export_action


def create_flint_model():
    flint = flint_model.FlintState()
    return flint


def create_manager():
    manager = ManageMainBehaviours()
    flintModel = create_flint_model()
    manager.setFlintModel(flintModel)
    return manager


def test_logbook(local_flint, metamgr):
    tango_metadata = metamgr[1]

    manager = create_manager()
    plot = PlotWindow()
    action = export_action.ExportToLogBookAction(plot, plot)
    action.setFlintModel(manager.flintModel())

    # The action is not available
    assert not action.isEnabled()

    # The action is now available
    manager.setTangoMetadataName(tango_metadata.name())
    assert action.isEnabled()

    # The can use it
    action.trigger()

    action.deleteLater()
    plot.deleteLater()


def test_logbook_send_data(local_flint):
    class MetadataMock:
        def __init__(self):
            self.data = None

        def uploadBase64(self, data):
            self.data = data

    model = create_flint_model()
    device = MetadataMock()
    model.setTangoMetadata(device)
    plot = PlotWindow()
    action = export_action.ExportToLogBookAction(plot, plot)
    action.setFlintModel(model)

    assert action.isEnabled()
    action.trigger()

    assert device.data is not None
    mimetype = b"data:image/png;base64,"
    assert device.data.startswith(mimetype)

    image = device.data[len(mimetype) :]
    image = base64.b64decode(image)
    magic = b"\x89\x50\x4e\x47\x0d\x0a\x1a\x0a"
    assert image.startswith(magic)

    action.deleteLater()
    plot.deleteLater()
