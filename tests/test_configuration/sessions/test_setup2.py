from bliss.shell.standard import *
from bliss.shell.cli.protected_dict import protect_after_setup

# Do not remove this print (used in tests)
print("TEST_SESSION2 INITIALIZED")
#

load_script("script1")


protect_after_setup("toto")

var1 = 1
var2 = 2

protect_after_setup(["var1", "var2", "var3"])
