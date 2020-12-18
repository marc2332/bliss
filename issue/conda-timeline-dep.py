

import subprocess
import json
from pprint import pprint
import os.path
import datetime
import io


def dump():
    print("Read deps")
    res = subprocess.check_output(["conda", "list", "--json"])
    data = json.loads(res)
    lib_deps = {}
    for lib_info in data:
        name = lib_info["name"]
        lib_deps[name] = lib_info

    for lib_info in lib_deps.values():
        name = lib_info["name"]
        print(f"Read {name} versions")
        res = subprocess.check_output(["conda", "search", f"{name}", "--json"])
        data = json.loads(res)

        versions = {}
        for v_info in data[name]:
            versions[v_info["version"]] = v_info
        lib_info["versions"] = versions
    return lib_deps


def read(filename):
    if os.path.exists(filename):
        with open(filename, "rt") as fp:
            return json.load(fp)
    else:
        data = dump()
        with open(filename, "wt") as fp:
            json.dump(lib_deps, fp)
        return data


data = read("deps.json")


with open("result", "wt") as writer:
    for lib_info in data.values():
        name = lib_info["name"]
        for v_info in lib_info["versions"].values():
            version = v_info["version"]
            if "timestamp" not in v_info:
                print(f"Skip {name} {version}")
                continue
            timestamp = v_info["timestamp"] // 1000
            date = datetime.datetime.fromtimestamp(timestamp).isoformat()
            try:
                writer.write(f"{name}\t{version}\t{date}\n")
            except Exception as e:
                print(e)
