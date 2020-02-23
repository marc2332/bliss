import datetime
import time
import tabulate
import logging

from bliss.scanning.chain import AcquisitionChain
from bliss.scanning.scan import Scan, ScanState, DataWatchCallback
from bliss.scanning.toolbox import ChainBuilder
from bliss.controllers.lima.lima_base import Lima
from bliss.common.utils import BOLD, RED

_log = logging.getLogger("bliss.scans")


__all__ = ("limastat", "limatake")


def limastat(*limadevs):
    """Perform and print test on saving performances for given lima devices.

    If no lima device is given in parameter, use active lima devices in current
    measurement group.
    """
    if not len(limadevs):
        limaused = list()

        builder = ChainBuilder([])
        for node in builder.get_nodes_by_controller_type(Lima):
            limaused.append(node.controller)

        if not limaused:
            raise RuntimeError("No active LIMA device in the current measurement group")
        limadevs = limaused

    stats = list()
    for lima in limadevs:
        name = lima.name
        hlen = lima._proxy.saving_statistics_history
        if hlen:
            sval = lima._proxy.saving_statistics
            cam_stat = [BOLD(name), hlen]
            cam_stat.append("{0:.2f} MB/sec".format(sval[3] / 1024. / 1024.))
            cam_stat.append("{0:.3f}".format(sval[2]))
            cam_stat.append("{0:.2f} MB/sec".format(sval[1] / 1024. / 1024.))
            cam_stat.append("{0:.2f} MB/sec".format(sval[0] / 1024. / 1024.))
            stats.append(cam_stat)
        else:
            stats.append([name, 0, "---", "---", "---", "---"])
    heads = [
        "camera",
        "history\nsize",
        "incoming\nspeed",
        "compression\nratio",
        "compression\nspeed",
        "write\nspeed",
    ]
    print("\n" + tabulate.tabulate(stats, heads, stralign="right") + "\n")


def _limatake_parse_args(args):
    alldict = dict()
    devdict = dict()
    for (name, value) in args.items():
        if type(value) == dict:
            if name not in devdict.keys():
                devdict[name] = dict()
            devdict[name].update(value)
        else:
            alldict[name] = value
    return alldict, devdict


def limatake(expotime, nbframes=1, save=False, run=True, **kwargs):
    """Perform an acquisition with lima devices active in current measurement
    group.

    - <expotime>: time in second to use for acquisition.
    - [<nbframes>]: number of frames to acquire (1 if not specified)

    Supplementary parameters can be given one by one or as a dictionary with the
    name of a Lima object.

    Scan parameters a fixed list.  ???

    All parameters not specified under a Lima device name are added to the list
    of acquisition parameters and passed to all cameras.

    Dictionaries for individual lima devices are only added as acquisition
    parameres to the corresponding camera.

    Example:
        ccd1={'saving_suffix': '.edf', 'saving_format': 'EDF'}
        limatake (0.1, 10, saving_frame_per_file=5, basler1=ccd1, save=True)

    """
    (all_args, dev_args) = _limatake_parse_args(kwargs)

    title = kwargs.get("title", "limatake")
    full_title = title + " {0:.4f} {1}".format(expotime, nbframes)

    lima_params = {
        "acq_nb_frames": nbframes,
        "acq_expo_time": expotime,
        "acq_mode": "SINGLE",
        "acq_trigger_mode": "INTERNAL_TRIGGER",
        "prepare_once": True,
        "start_once": False,
    }
    if save is True:
        lima_params["saving_statistics_history"] = int(nbframes)

    # merge all other non Lima device related parameters
    lima_params.update(all_args)

    chain = AcquisitionChain(parallel_prepare=True)
    builder = ChainBuilder([])

    limaused = list()
    limadevs = list()
    for node in builder.get_nodes_by_controller_type(Lima):
        limaused.append(node)
        limadevs.append(node.controller)

        # get the parameters for every Lima device
        acq_params = lima_params
        acq_params.update(dev_args.get(node.controller.name, {}))

        node.set_parameters(acq_params=acq_params)
        chain.add(node)

    # raise an exception if no detector was found in the measurement group
    if not limaused:
        raise RuntimeError("No active LIMA device in the current measurement group")

    # todo to be changed in Bliss
    # Today, the first top master that finishes, stops all others!!!!!
    top_masters = [x.identifier for x in chain._tree.children("root")]
    for top_master in top_masters:
        top_master.terminator = False

    scan_info = lima_params
    scan_info.update(acq_params)
    scan_info["title"] = "limatake {0:.4f} {1}".format(expotime, nbframes)
    scan = Scan(
        chain,
        scan_info=scan_info,
        name=full_title,
        save=save,
        data_watch_callback=LimaTakeDisplay(*limadevs),
    )
    print(scan.acq_chain._tree)
    if run == True:
        scan.run()

    return scan


class LimaTakeDisplay(DataWatchCallback):
    """Callback used by limatake to print acquisition status.
    """

    HEADER = (
        "Scan {scan_nb} {start_time_str} {filename} "
        + "{session_name} user = {user_name}\n"
        + "{title}"
    )

    def __init__(self, *lima_objs):
        self.__limas = lima_objs

    def on_state(self, state):
        return True

    def on_scan_new(self, scan, info):
        print(self.HEADER.format(**info))
        self.__state = None
        self.__infos = dict()
        self.__save_flag = info.get("save", False)

        for lima in self.__limas:
            self.__infos[lima.name] = 0

    def on_scan_end(self, info):
        msg = self.__update_cam_infos()
        print(msg)
        start = datetime.datetime.fromtimestamp(info["start_timestamp"])
        end = datetime.datetime.fromtimestamp(time.time())
        msg = "Finished (took {0})\n".format(end - start)
        print(msg)

    def __update_cam_infos(self):
        for cam in self.__limas:
            last_acq = cam._proxy.last_image_ready + 1
            msg = "acq #{0}".format(last_acq)
            if self.__save_flag:
                last_saved = cam._proxy.last_image_saved + 1
                msg += " save #{0}".format(last_saved)
            last_status = cam._proxy.acq_status
            if last_status == "Ready":
                msg = BOLD(msg)
            elif last_status == "Fault":
                msg = RED(msg)
            self.__infos[cam.name] = msg
        msg = ""
        for (name, value) in self.__infos.items():
            msg += "{0} {1}  ".format(BOLD(name), value)
        return msg

    def on_scan_data(self, data_events, data_nodes, info):
        # look for scan state
        state = info.get("state", None)
        if state != self.__state:
            self.__state = state
            if state == ScanState.PREPARING:
                msg = "Preparing "
                for lima in self.__limas:
                    msg += "{0} ".format(lima.name)
                print(msg + "...")
            if state == ScanState.STARTING:
                print("Running ...")
        if state == ScanState.STARTING:
            # print last images acquired and saved
            msg = self.__update_cam_infos()
            print(msg + "\r", end="")
