from bliss.common.scans import loopscan
from bliss.setup_globals import diode1
from bliss.scanning.scan_saving import ScanSaving
from bliss import current_session
from bliss.scanning.scan import Scan
from bliss.icat.definitions import Definitions
from pprint import pprint


def demo_with_technique():
    """ a demo procedure using a custom scan saving"""

    scan_saving = ScanSaving("my_custom_scansaving")

    # how is it suppsed to work with the dataset name?
    ds_name = current_session.scan_saving.dataset
    ds_name += "_b"

    # create a new dataset ony for the scans in here.
    scan_saving.newdataset(ds_name)

    definitions = Definitions()

    scan_saving.dataset_object.add_technique(definitions.techniques.FLUO)

    # just prepare a custom scan ...
    ls = loopscan(3, .1, diode1, run=False)
    s = Scan(ls.acq_chain, scan_saving=scan_saving)

    # add some metadata before the scan runs
    scan_saving.dataset_object["FLUO_i0"] = str(17.1)

    # run the scan[s]
    s.run()

    # add some metadata after the scan runs
    scan_saving.dataset_object["FLUO_it"] = str(18.2)

    # just for the debug print at the end
    node = scan_saving.dataset_object.node

    # should this print be obligatory?
    scan_saving.dataset_object.check_metatdata_consistency()

    # close the dataset
    scan_saving.enddataset()

    # just for diagostics: print all collected metadata
    pprint(node.metadata)

    # just see if dataset is marked as closed
    print("is_closed: ", node.is_closed)
