import sys
import pickle
import logging
import logging.handlers
from logging.handlers import RotatingFileHandler
import struct
import argparse
import pathlib

from gevent.server import StreamServer


INITIALIZED_SESSIONS = []  # store names of initialized sessions for creating FileHandlers

_log = logging.getLogger("log_server")


class Handler:
    def __init__(self, db_path, log_size):
        self.db_path = db_path
        self.log_size = log_size

    def __call__(self, socket, address):
        while True:
            chunk = socket.recv(4)
            if len(chunk) < 4:
                break
            slen = struct.unpack(">L", chunk)[0]
            chunk = socket.recv(slen)
            if not len(chunk):  # socket closed by client
                break

            while len(chunk) < slen:
                data = socket.recv(slen - len(chunk))
                if not len(data):  # socket closed by client
                    return
                chunk = chunk + data
            obj = pickle.loads(chunk)

            check_session(obj["session"], self.db_path, self.log_size)

            # adding a 'session' argument to log messages
            record = logging.makeLogRecord(obj)
            handle_log_record(record)


def handle_log_record(record):
    logger = logging.getLogger(record.name)
    logger.handle(record)


def check_session(session, root_path, log_size=1):
    """
    Check if a session has a RotatingFileHandler and if not it
    creates one
    """
    if session not in INITIALIZED_SESSIONS:
        # creating handler
        dir_path = pathlib.Path(root_path)
        if not dir_path.exists():
            dir_path.mkdir()

        file_path = dir_path / f"{session}.log"
        _log.info(f"Appending to file {file_path}")
        handler = RotatingFileHandler(
            file_path, maxBytes=1024 ** 2 * log_size, backupCount=10
        )

        def filter_func(rec):
            # filter if a message is for the right session
            # and consequently the right log file
            if rec.session == session:
                return True
            return False

        formatter = logging.Formatter(
            "%(asctime)s %(session)s %(name)s %(levelname)s : %(msg)s"
        )  # adapt to needs
        handler.addFilter(filter_func)
        handler.setFormatter(formatter)
        logging.getLogger().addHandler(handler)

        INITIALIZED_SESSIONS.append(session)


def main(args=None):
    # logging of the logserver to stdout
    handler = logging.StreamHandler(sys.stdout)
    _log.addHandler(handler)
    _log.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(message)s"
    )  # metadata are also added by beacon logger

    handler.setFormatter(formatter)

    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, dest="port")
    p.add_argument(
        "--log-output-folder", "--log_output_folder", type=str, dest="log_output_folder"
    )
    p.add_argument("--log-size", "--log_size", type=float, dest="log_size")
    _options = p.parse_args(args)

    _log.info(f"Initialize StreamServer on port {_options.port}")
    server = StreamServer(
        ("0.0.0.0", _options.port),
        Handler(_options.log_output_folder, _options.log_size),
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
