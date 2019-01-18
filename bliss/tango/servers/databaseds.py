"""Run the tango.databaseds.database server with bliss db_access."""


from tango.databaseds import db_access
from tango.databaseds.database import main as base_main

from bliss.tango import db_access as local_db_access


def main(args=None):
    # Give priority to the bliss db_access module
    db_access.__path__ = local_db_access.__path__ + db_access.__path__
    db_access.__package__ = "bliss.tango.db_access"
    # Safety check
    from tango.databaseds.db_access import beacon

    assert beacon.__file__.startswith(local_db_access.__path__[0])
    # Run
    base_main(args)


if __name__ == "__main__":
    main()
