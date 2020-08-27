"""Run the tango.databaseds.database server with bliss db_access."""
import sys
import argparse

from tango.databaseds import db_access
from tango.databaseds.database import main as base_main
from bliss.tango import db_access as local_db_access


def main(args=None):
    db_access.__path__ = local_db_access.__path__ + db_access.__path__

    # Display message (used for synchronization with parent process)
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, dest="port")
    known_args, _ = p.parse_known_args(sys.argv)
    print(f"Tango database starting on port {known_args.port} ...", flush=True)

    # Run
    base_main(args)


if __name__ == "__main__":
    main()
