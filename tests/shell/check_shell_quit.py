from bliss.shell.cli import repl

s = repl.initialize("test_session")
print("Script: closing session ...")
s.close()
print("Script: session closed.")
