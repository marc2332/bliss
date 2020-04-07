from bliss.shell.standard import *
from bliss import is_bliss_shell

# Do not remove this print (used in tests)
print("TEST_SESSION2 INITIALIZED")
#

load_script("script1")

if is_bliss_shell():
    protect("toto")

var1 = 1
var2 = 2

if is_bliss_shell():
    protect(["var1", "var2", "var3"])
