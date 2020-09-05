"""This replaces `LimcaCCDs` for testing purposes"""

import sys
import os
import six
import atexit
import PyTango
from Lima.Server import LimaCCDs


def main(args=None):
    args = list(args or sys.argv)
    args[0] = "LimaCCDs"
    pid = os.getpid()

    def eprint(msg):
        print(f"pid={pid} {args}: {msg}", file=sys.stderr, flush=True)

    def finalize():
        eprint("Exiting")

    atexit.register(finalize)

    eprint("connection to tango database ...")
    db = PyTango.Database()
    db.build_connection()

    LimaCCDs.verboseLevel = 0
    for option in args:
        if option.startswith("-v"):
            try:
                LimaCCDs.verboseLevel = int(option[2:])
            except Exception:
                pass

    pytango_ver = PyTango.__version_info__[:3]

    try:
        eprint("instantiate Util (1) ...")
        py = PyTango.Util(args)

        eprint("add LimcaCCDs class ...")
        py.add_TgClass(LimaCCDs.LimaCCDsClass, LimaCCDs.LimaCCDs, "LimaCCDs")
        try:
            LimaCCDs.declare_camera_n_commun_to_tango_world(py)
        except Exception:
            import traceback

            traceback.print_exc()

        eprint("instantiate Util (2) ...")
        U = PyTango.Util.instance()

        # create ct control
        control = LimaCCDs._get_control()
        if pytango_ver >= (8, 1, 7) and control is not None:
            eprint("server_init (with control) ...")
            master_dev_name = LimaCCDs.get_lima_device_name()
            beamline_name, _, camera_name = master_dev_name.split("/")
            name_template = "{0}/{{type}}/{1}".format(beamline_name, camera_name)
            # register Tango classes corresponding to CtControl, CtImage, ...
            server, ct_map = LimaCCDs.create_tango_objects(control, name_template)
            tango_classes = set()
            for name, (tango_ct_object, tango_object) in six.iteritems(ct_map):
                tango_class = server.get_tango_class(tango_object.class_name)
                tango_classes.add(tango_class)
            for tango_class in tango_classes:
                py.add_class(tango_class.TangoClassClass, tango_class)

            U.server_init()

            LimaCCDs.export_ct_control(ct_map)

        else:
            eprint("server_init ...")
            U.server_init()

        # Configurations management (load default or custom config)
        eprint("configure ...")
        dev = U.get_device_list_by_class("LimaCCDs")
        if dev:
            dev[0].apply_config()

        try:
            LimaCCDs.export_default_plugins()
        except:
            import traceback

            traceback.print_exc()

        eprint("server_run ...")
        U.server_run()

    except PyTango.DevFailed as e:
        eprint(f"-------> Received a DevFailed exception: {e}")
    except Exception as e:
        eprint(f"-------> An unforeseen exception occurred: {e}")
        # import traceback
        # traceback.print_exc()


if __name__ == "__main__":
    main()
