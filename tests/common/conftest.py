from ..motors.conftest import *
from bliss.common.logtools import logbook_printer


@pytest.fixture
def log_shell_mode():
    logbook_printer.add_stdout_handler()
    yield
    logbook_printer.remove_stdout_handler()
