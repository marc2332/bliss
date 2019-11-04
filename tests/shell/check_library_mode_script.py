import sys

from bliss import is_bliss_shell
from bliss.config import static

config = static.get_config()
session = config.get("flint")
session.setup()

[print(x) for x in sys.modules.keys() if "bliss.shell" in x]


print("SHELL_MODE:", is_bliss_shell())
