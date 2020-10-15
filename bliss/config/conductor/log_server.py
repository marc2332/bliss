import sys
import pickle
import logging
from logging.handlers import RotatingFileHandler
import struct
import argparse
import pathlib

from gevent.server import StreamServer


_log = logging.getLogger("log_server")


class LogServer(StreamServer):
    """Process logging record received inside the `handle` function,
    and dispatch them into different logging handlers."""

    _handlers = {}
    """
    Store initialized FileHandlers.

    There is a single handler per session.
    """

    def __init__(self, listener, db_path, log_size):
        self.db_path = db_path
        self.log_size = log_size
        super(LogServer, self).__init__(listener, self.handle)

    def handle(self, socket, address):
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
            record_dict = pickle.loads(chunk)

            self.prepare_handler(record_dict, self.db_path, self.log_size)

            # adding a 'session' argument to log messages
            record = logging.makeLogRecord(record_dict)
            self.log_record(record)

    def prepare_handler(self, record_dict, root_path, log_size):
        """
        Check if a session has a RotatingFileHandler and if not it
        creates one.
        """
        session = record_dict["session"]
        if session not in self._handlers:
            handler = self.create_bliss_session_handler(
                self.db_path, session, self.log_size
            )
            self._handlers[session] = handler
            root_logger = logging.getLogger()
            root_logger.addHandler(handler)

    def log_record(self, record):
        logger = logging.getLogger(record.name)
        logger.handle(record)

    def create_bliss_session_handler(self, dir_path, session, log_size):
        """Create a dedicated handler to store log in a file for a specific
        BLISS session"""

        # create root directory if needed
        dir_path = pathlib.Path(dir_path)
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
        return handler


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
    options = p.parse_args(args)

    _log.info(f"Initialize LogServer on port {options.port}")

    server = LogServer(
        ("0.0.0.0", options.port), options.log_output_folder, options.log_size
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
