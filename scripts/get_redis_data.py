import sys
from bliss.config import settings
from bliss.config.conductor import client
from bliss.data import node
from bliss.shell.cli.user_dialog import UserMsg, UserYesNo

from distutils import util


def yesno(msg):
    _message = msg + "(y/n) "
    _ans = input(_message)
    try:
        return util.strtobool(_ans)
    except:
        return False


try:
    key_name = sys.argv[1]
except:
    print(f"\n  Usage: {sys.argv[0]} <redis_keys_pattern>")
    print(
        '    Example: \n  python ./get_redis_data.py "session_dcm:data:id21:inhouse:laser:223_timescan:timer*_data" \n'
    )
    exit()

db_cnx = client.get_redis_connection(db=1)

print(f"reading Keys from {key_name}")
keys_to_read = [
    keys.strip("_data") for keys in settings.scan(f"{key_name}*", connection=db_cnx)
]
for kk in keys_to_read:
    if yesno(f"Do you want to read {kk} ? "):
        file_name = kk.replace("/", "_")
        file_name = file_name.replace(":", "_") + ".txt"
        nn = node.get_nodes(kk)[0]
        with open(file_name, mode="a+") as f:
            f.write("\n".join(str(line) for line in nn.get(0, -1)))
