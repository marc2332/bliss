#!/usr/bin/env python

from contextlib import contextmanager
import os
import sys
from collections import namedtuple
import atexit
import subprocess
import redis
import socket
import time
import threading
from tango import DeviceProxy, DevFailed
from contextlib import contextmanager
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


def start_beacon():
    redis_uds = os.path.join(BEACON_DB_PATH, "redis_demo.sock")
    ports = namedtuple("Ports", "redis_port tango_port beacon_port")(
        int(CMDLINE_ARGS["--redis-port"]),
        int(CMDLINE_ARGS["--tango-port"]),
        int(CMDLINE_ARGS["--beacon-port"]),
    )
    args = [
        "--port=%d" % ports.beacon_port,
        "--redis_port=%d" % ports.redis_port,
        "--redis_socket=" + redis_uds,
        "--db_path=" + BEACON_DB_PATH,
        "--posix_queue=0",
        "--tango_port=%d" % ports.tango_port,
    ]

    proc = subprocess.Popen(BEACON + args, stderr=subprocess.PIPE)
    wait_for(proc.stderr, "database started on port")

    time.sleep(
        1
    )  # ugly synchronisation, would be better to use logging messages? Like 'post_init_cb()' (see databaseds.py in PyTango source code)

    # important: close to prevent filling up the pipe as it is not read during tests
    proc.stderr.close()

    os.environ["TANGO_HOST"] = "%s:%d" % (socket.gethostname(), ports.tango_port)
    os.environ["BEACON_HOST"] = "%s:%d" % (socket.gethostname(), ports.beacon_port)
    os.environ["BEACON_REDIS_PORT"] = "%d" % ports.redis_port

    # disable .rdb files saving (redis persistence)
    r = redis.Redis(host="localhost", port=ports.redis_port)
    r.config_set("SAVE", "")
    del r

    return proc


def wait_server_to_be_started(device_fqdn, err_msg):
    t0 = time.time()

    while True:
        try:
            dev_proxy = DeviceProxy(device_fqdn)
            dev_proxy.ping()
            dev_proxy.state()
        except DevFailed as e:
            time.sleep(0.1)
        else:
            break

        time.sleep(1)

        if time.time() - t0 > 10:
            raise RuntimeError(err_msg)

        return dev_proxy


def start_tango_servers():
    wait_tasks = []
    processes = []

    for device_name, cmdline in (
        ("id00/limaccds/simulator1", ("LimaCCDs", "simulator")),
        (
            "id00/limaccds/slits_simulator",
            ("SlitsSimulationLimaCCDs", "slits_simulator"),
        ),
        ("id00/limaccds/tomo_simulator", ("TomoSimulationLimaCCDs", "tomo_simulator")),
        ("id00/metadata/demo", ("MetadataManager", "demo")),
        ("id00/metaexp/demo", ("MetaExperiment", "demo")),
        ("id00/bliss_nxwriter/demo_session", ("NexusWriterService", "demo")),
    ):
        device_fqdn = "tango://{}/{}".format(os.environ["TANGO_HOST"], device_name)

        processes.append(subprocess.Popen(cmdline))

        wait_tasks.append(
            threading.Thread(
                target=wait_server_to_be_started,
                args=(device_fqdn, f"{device_fqdn} is not running"),
            )
        )
        wait_tasks[-1].start()

    for task in wait_tasks:
        task.join()

    return processes


beacon_process = start_beacon()
tango_processes = start_tango_servers()

print(
    f"""
##################################################################################"
# start BLISS in another Terminal using                                          #"
# > TANGO_HOST={os.environ["TANGO_HOST"]} BEACON_HOST={os.environ["BEACON_HOST"]} bliss -s demo_session #"
#                                                                                #"
# press ctrl+c to quit this process                                              #"
##################################################################################"""
)

try:
    while True:
        time.sleep(30)
except:
    for p in tango_processes:
        print("terminating", p.pid)
        p.terminate()
        p.wait()
        print("  - ok")
    print("terminating Beacon")
    beacon_process.terminate()
    beacon_process.wait()
    print("done")
