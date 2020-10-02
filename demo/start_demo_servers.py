#!/usr/bin/env python

import os
import sys
from collections import namedtuple
import subprocess
import redis
import socket
import contextlib
import time
import tempfile
import shutil
import threading
from tango import DeviceProxy, DevFailed
from docopt import docopt

BLISS = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BEACON = [sys.executable, "-m", "bliss.config.conductor.server"]
BEACON_DB_PATH = os.path.join(BLISS, "demo", "demo_configuration")
CMDLINE_ARGS = docopt(
    """
Usage: start_demo_servers [--beacon-port=<beacon_port>] [--tango-port=<tango_port>] [--redis-port=<redis_port>]

Options:
    --beacon-port=<beacon_port>   Beacon server port [default: 10001]
    --tango-port=<tango_port>     Tango database server port [default: 10000]
    --redis-port=<redis_port>     Redis server port [default: 10002]
"""
)


def wait_for(stream, target):
    def do_wait_for(stream, target, data=b""):
        target = target.encode()
        while target not in data:
            char = stream.read(1)
            if not char:
                raise RuntimeError(
                    "Target {!r} not found in the following stream:\n{}".format(
                        target, data.decode()
                    )
                )
            data += char

    return do_wait_for(stream, target)


@contextlib.contextmanager
def setup_resource_files():
    """Setup the configuration files"""
    tmp_dir = tempfile.mkdtemp(prefix="demo_resources")
    directory = os.path.join(tmp_dir, "configuration")
    shutil.copytree(BEACON_DB_PATH, directory)
    try:
        yield directory
    finally:
        shutil.rmtree(tmp_dir)


def cleanup_processes(processes):
    for p in processes:
        try:
            print("terminating", p.pid)
            p.terminate()
            p.wait(timeout=10)
            print("  - ok")
        except Exception:
            print("  - still running")


def start_beacon(db_path):

    redis_uds = os.path.join(db_path, "redis_demo.sock")
    ports = namedtuple("Ports", "redis_port tango_port beacon_port")(
        int(CMDLINE_ARGS["--redis-port"]),
        int(CMDLINE_ARGS["--tango-port"]),
        int(CMDLINE_ARGS["--beacon-port"]),
    )
    args = [
        "--port=%d" % ports.beacon_port,
        "--redis_port=%d" % ports.redis_port,
        "--redis_socket=" + redis_uds,
        "--db_path=" + db_path,
        "--tango_port=%d" % ports.tango_port,
        # "--log-level=INFO",
        # "--tango_debug_level=1",
    ]

    proc = subprocess.Popen(BEACON + args)
    try:
        wait_tango_device(
            f"tango://localhost:{ports.tango_port}/sys/database/2",
            "Tango database is not running",
        )

        time.sleep(1)  # Waiting for Redis?

        os.environ["TANGO_HOST"] = "%s:%d" % (socket.gethostname(), ports.tango_port)
        os.environ["BEACON_HOST"] = "%s:%d" % (socket.gethostname(), ports.beacon_port)
        os.environ["BEACON_REDIS_PORT"] = "%d" % ports.redis_port

        # disable .rdb files saving (redis persistence)
        r = redis.Redis(host="localhost", port=ports.redis_port)
        r.config_set("SAVE", "")
        del r
    except BaseException:
        cleanup_processes([proc])
        raise

    return proc


def wait_tango_device(admin_device_fqdn, err_msg, timeout=10):
    t0 = time.time()
    exception = None

    while True:
        try:
            dev_proxy = DeviceProxy(admin_device_fqdn)
            dev_proxy.ping()
        except DevFailed as e:
            exception = e
            time.sleep(0.5)
        else:
            break

        if time.time() - t0 > timeout:
            raise RuntimeError(err_msg) from exception

    return dev_proxy


def start_tango_servers():
    wait_tasks = []
    processes = []

    try:

        for device_name, cmdline, server_name in (
            ("id00/limaccds/simulator1", ("LimaCCDs", "simulator"), "LimaCCDs"),
            (
                "id00/limaccds/slits_simulator",
                ("SlitsSimulationLimaCCDs", "slits_simulator"),
                "LimaCCDs",
            ),
            (
                "id00/limaccds/tomo_simulator",
                ("TomoSimulationLimaCCDs", "tomo_simulator"),
                "LimaCCDs",
            ),
            (
                "id00/limaccds/diff_simulator",
                ("DiffSimulationLimaCCDs", "diff_simulator"),
                "LimaCCDs",
            ),
            (
                "id00/metadata/demo_session",
                ("MetadataManager", "demo"),
                "MetadataManager",
            ),
            ("id00/metaexp/demo_session", ("MetaExperiment", "demo"), "MetaExperiment"),
            (
                "id00/bliss_nxwriter/demo_session",
                ("NexusWriterService", "demo"),
                "NexusWriter",
            ),
        ):
            fqdn_prefix = f"tango://{os.environ['TANGO_HOST']}"
            device_fqdn = f"{fqdn_prefix}/{device_name}"
            personal_name = cmdline[-1]
            admin_device_fqdn = f"{fqdn_prefix}/dserver/{server_name}/{personal_name}"

            processes.append(subprocess.Popen(cmdline))

            wait_tasks.append(
                threading.Thread(
                    target=wait_tango_device,
                    args=(admin_device_fqdn, f"{device_fqdn} is not running"),
                )
            )
            wait_tasks[-1].start()

        for task in wait_tasks:
            task.join()
    except BaseException:
        cleanup_processes(processes)
        raise

    return processes


def bordered_text(text):
    lines = text.splitlines()
    width = max([len(l) for l in lines])
    for i, l in enumerate(lines):
        before = (width - len(l)) // 2
        after = (width - len(l) + 1) // 2
        l = "# " + " " * before + l + " " * after + " #"
        lines[i] = l
    lines.insert(0, "#" * (width + 4))
    lines.append("#" * (width + 4))
    return "\n".join(lines)


def run(db_path):
    beacon_process = start_beacon(db_path)
    tango_processes = start_tango_servers()

    text = f"""Start BLISS in another Terminal using

> TANGO_HOST={os.environ["TANGO_HOST"]} BEACON_HOST={os.environ["BEACON_HOST"]} bliss -s demo_session

Press CTRL+C to quit this process
"""
    print(bordered_text(text))

    try:
        threading.Event().wait()
    except BaseException:
        cleanup_processes(tango_processes + [beacon_process])


with setup_resource_files() as db_path:
    run(db_path)
    print("done")
