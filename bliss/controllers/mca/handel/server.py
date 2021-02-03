"""Serve the handel interface over the network using bliss rpc.

This requires python3, handel.

Usage:

    $ ./bliss-handel-server 8888
    Serving handel on tcp://0.0.0.0:8888 ...
"""

import os
import argparse
import logging
from bliss.comm import rpc
from bliss import release
import bliss

# ??? gevent imported from handel ???
from bliss.controllers.mca.handel import gevent
from bliss.config.static import get_config as get_beacon_config

import bliss.controllers.mca.handel.interface as hi

_logger = logging.getLogger(__name__)

try:
    import git
except ImportError:
    # Make it pass for the Sphinx API documentation
    git = None


# Run server
def run(bind="0.0.0.0", port=8000, verbose=0):

    if git is None:
        raise ImportError("git library not found")

    # Logging.
    logger = logging.getLogger("HANDEL_rpc")

    # file handler
    fh = logging.FileHandler("handel_server.log")
    fh.setLevel(logging.DEBUG)

    # console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)

    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    # datefmt='%m-%d-%Y %I:%M:%S %p'
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)

    logger.addHandler(ch)
    logger.addHandler(fh)

    if verbose == 1:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)

    # Just warn about missing git support, it's not a big problem.
    if git is None:
        logger.warning("git library not found")
    else:
        # Retrieve GIT repo info.
        try:
            bpath = bliss.__path__[0]
            try:
                os.chdir(bpath)
                logger.debug(f"now in {bpath}")
            except Exception:
                logger.debug(f"Cannot go to bliss repo dir {bpath}")
        except Exception:
            logger.debug("canot find bliss path")
        try:
            repo = git.Repo(search_parent_directories=True)
            sha = repo.head.object.hexsha
            branch = repo.active_branch.name
            last_commit_date = repo.head.object.committed_datetime.isoformat()
        except git.InvalidGitRepositoryError as excp:  # noqa: F841
            sha = "not in git repo directory"
            branch = "not in git repo directory"
            last_commit_date = "not in git repo directory"
        except TypeError as excp:  # noqa: F841
            sha = "detached head ?"
            branch = "detached head ?"
            last_commit_date = "detached head ?"

    logger.info(f"BLISS version = {release.version}")

    if git is not None:
        logger.debug(f"      commit = {sha}")
        logger.debug(f"      branch = {branch}")
        logger.debug(f"      last commit = {last_commit_date}")
    try:
        hi.init_handel()
        server = rpc.Server(hi, stream=True)
        server.bind(access)
        logger.info(f"READY - (Serving handel on {access}).")
        try:
            # start RPC server
            server.run()
        except KeyboardInterrupt:
            print("Interrupted (by Ctrl-c).")
        finally:
            server.close()
    finally:
        hi.exit()


# Parsing


# Startup script arguments parsing.
def parse_args(args=None):
    parser = argparse.ArgumentParser(
        prog="handel-server",
        description="Serve the handel interface over the network using bliss rpc",
    )
    parser.add_argument(
        "--bind",
        "-b",
        default="0.0.0.0",
        metavar="address",
        help="Specify alternate bind address [default: all interfaces]",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        default="0",
        metavar="verbosity",
        help="Specify level of verbosity [default: 0]",
    )
    parser.add_argument(
        "port",
        action="store",
        default=8000,
        type=int,
        nargs="?",
        help="Specify alternate port [default: 8000]",
    )
    return parser.parse_args(args)


def main(args=None):
    namespace = parse_args(args)
    print("starting handel server")

    # ???
    gevent.patch()
    run(namespace.bind, namespace.port, int(namespace.verbose))


if __name__ == "__main__":
    main()
