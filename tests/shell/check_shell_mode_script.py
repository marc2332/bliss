from bliss.shell.cli import repl

from bliss import is_bliss_shell

from prompt_toolkit.input.defaults import create_pipe_input
from prompt_toolkit.output import DummyOutput


inp = create_pipe_input()

cli = repl.cli(
    input=inp, output=DummyOutput(), session_name="flint", expert_error_report=True
)

print("SHELL_MODE:", is_bliss_shell())
