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
import git
from git import InvalidGitRepositoryError

# ??? gevent imported from handel ???
from bliss.controllers.mca.handel import gevent

import bliss.controllers.mca.handel.interface as hi


# Run server
def run(bind="0.0.0.0", port=8000, verbose=0):

    # Logging.
    logger = logging.getLogger("HANDEL_rpc")
    log_handler = logging.StreamHandler()
    if verbose == 1:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)
    # log_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    log_format = logging.Formatter("%(levelname)s - %(message)s")
    log_handler.setFormatter(log_format)
    logger.addHandler(log_handler)
    logger.error("LOGGER ERROR")
    logger.warning("LOGGER WARNING")
    logger.info("LOGGER INFO")
    logger.critical("LOGGER CRITICAL")
    logger.debug("LOGGER DEBUG")

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
    except InvalidGitRepositoryError:
        sha = "not in git repo directory"
        branch = "not in git repo directory"
        last_commit_date = "not in git repo directory"
    logger.info(f"verbose={verbose}")
    logger.info(f"BLISS version = {release.version}")
    logger.debug(f"      commit = {sha}")
    logger.debug(f"      branch = {branch}")
    logger.debug(f"      last commit = {last_commit_date}")

    access = "tcp://{}:{}".format(bind, port)
    try:
        hi.init_handel()
        server = rpc.Server(hi, stream=True)
        server.bind(access)
        logger.info("Serving handel on {} ...".format(access))
        try:
            server.run()
        except KeyboardInterrupt:
            print("Interrupted.")
        finally:
            server.close()
    finally:
        hi.exit()


# Parsing


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


# Main function


def main(args=None):
    namespace = parse_args(args)

    # ???
    gevent.patch()
    run(namespace.bind, namespace.port, int(namespace.verbose))


if __name__ == "__main__":
    main()
