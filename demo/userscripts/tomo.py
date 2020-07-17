"""Mimic tomo sequences in Bliss with sinogram re-emission

Can be run as script:

    flint()
    import os
    userscripts = os.path.join(os.getcwd(), "demo", "userscripts")
    user_script_homedir(userscripts)
    tomo = user_script_load("tomo.py", export_global=False)
    tomo.fullfield_tomo(demo_session, expo=0.01)
"""

import numpy
import gevent
from bliss.common import scans
from bliss.scanning.chain import AcquisitionChannel
from bliss.config.streaming import StreamStopReadingHandler
from bliss.data.node import get_node
from bliss.scanning.group import Sequence


class ScanReEmitter(gevent.Greenlet):
    def __init__(self, db_name, sequence, channelinfo, filter=None):
        self.db_name = db_name
        self.sequence = sequence
        self.channelinfo = channelinfo
        self.stop_handler = None
        self.filter = filter
        super().__init__()

    @property
    def custom_channels(self):
        return self.sequence.custom_channels

    def stop(self, timeout=None):
        try:
            self.stop_handler.stop()
        except AttributeError:
            pass
        self.join(timeout=timeout)

    def _run(self):
        self.stop_handler = StreamStopReadingHandler()
        try:
            it = get_node(self.db_name).iterator
            for event in it.walk_events(
                filter=self.filter, stream_stop_reading_handler=self.stop_handler
            ):
                if event.type == event.type.END_SCAN:
                    break
                elif event.type == event.type.NEW_DATA:
                    infos = self.channelinfo.get(event.node.name, [])
                    for info in infos:
                        self.reemit(event, info.get("name"), info.get("process"))
        finally:
            self.stop_handler = None

    def reemit(self, event, name, process=None):
        try:
            channel = self.custom_channels.get(name)
            if channel is None:
                return
            data = event.data.data
            if callable(process):
                data = process(data)
            channel.emit(data)
        except Exception as e:
            raise ValueError(f"Error re-emitting {name}") from e


def fullfield_tomo(session, nchunks=4, expo=1e-6):
    mca = session.env_dict["mca1"]
    # Lima does not have a 1D ROI yet
    detector = mca.counter_groups.spectrum.spectrum_det0
    # Session does not have a rotation
    rotmot = session.env_dict["sy"]
    rotmot.limits = -10000, 10000
    rotmot.velocity = 250000
    rotmot.acceleration = 100000
    npixels = detector.shape[0]

    # Prepare the scans
    chunkrange = 180 // nchunks
    chunks = numpy.arange(0, 180, chunkrange)
    rotinc = 1
    nrot = 0
    nrots = (180 - 0) // rotinc

    # FIXME: Lots of duplication, this should be generated from the defined custom_channels
    acquisition_chain = {
        # This name have to be bliss.scanning.group.GroupingMaster.name
        "GroupingMaster": {
            "master": {
                "scalars": ["translation", "rotation"],
                "scalars_units": {"translation": None, "rotation": "degree"},
            },
            "scalars": ["sinogram"],
            "scalars_units": {"sinogram": None},
        }
    }
    scan_info = {
        "acquisition_chain": acquisition_chain,
        "type": "sinogram",
        "data_dim": 2,
        "count_time": expo,
        "requests": {
            "rotation": {
                "start": 0,
                "stop": 180,
                "points": nrots * npixels,
                "axis-points": nrots,
                "axis-kind": "slow",
            },
            "translation": {
                "start": 0,
                "stop": npixels - 1,
                "points": nrots * npixels,
                "axis-points": npixels,
                "axis-kind": "fast",
            },
        },
    }

    seq = Sequence(title="halfturn", scan_info=scan_info)

    # Prepare group channels
    def replicate(angles):
        return numpy.repeat(angles, npixels)

    def flatten(spectra):
        return numpy.array(spectra).flatten()

    def translations(spectra):
        return flatten([numpy.arange(npixels)] * len(spectra))

    channelmap = {}
    seq.add_custom_channel(AcquisitionChannel("translation", numpy.float, ()))
    seq.add_custom_channel(AcquisitionChannel("rotation", numpy.float, ()))
    seq.add_custom_channel(AcquisitionChannel("sinogram", numpy.float, ()))
    channelmap[f"axis:{rotmot.name}"] = [{"name": "rotation", "process": replicate}]
    channelmap[detector.fullname] = [
        {"name": "sinogram", "process": flatten},
        {"name": "translation", "process": translations},
    ]

    session.scan_saving.newdataset("")
    print(session.scan_saving.filename)
    with seq.sequence_context() as scan_seq:
        # Get darks
        print("Dark ...")
        scan = scans.loopscan(10, expo, detector, name="dark", run=False)
        scan_seq.add_and_run(scan)
        for start in chunks:
            # Get references
            print("References ...")
            scan = scans.loopscan(10, expo, detector, name="references", run=False)
            scan_seq.add_and_run(scan)
            stop = start + chunkrange - rotinc
            nroti = int((stop - start + 1) / rotinc + 0.5)
            nsteps = nroti - 1
            nrot += nroti
            print(f"Rotate {start} -> {stop} ...")
            scan = scans.ascan(
                rotmot,
                start,
                stop,
                nsteps,
                expo,
                detector,
                run=False,
                title="projections",
            )
            scan_seq.add(scan)
            gscan = gevent.spawn(scan.run)
            while scan.node is None:
                gevent.sleep(0.1)  # do something better
            greemit = ScanReEmitter(scan.node.db_name, seq, channelmap)
            greemit.start()
            try:
                gscan.get()
            finally:
                greemit.get()
    data = seq.scan.get_data()
    npixels = npixels * nrot
    assert nrot == nrots
    assert len(data["sinogram"]) == npixels
    assert len(data["rotation"]) == npixels
    assert len(data["translation"]) == npixels
