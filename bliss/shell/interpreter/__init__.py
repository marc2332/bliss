#from types import ModuleType
from bliss import setup_globals
import sys

def start_interpreter(setup_file, config_objects_names, input_queue, output_queue):
    interpreter = __import__("interpreter", globals(), locals(), [])

    i = interpreter.init(input_queue, output_queue)
  
    """globals_module = ModuleType("globals")
    sys.modules["khoros.interpreter"].globals = globals_module
    sys.modules["khoros.interpreter.globals"] = globals_module 

    i.locals = globals_module.__dict__
    """
    i.locals = setup_globals.__dict__ #.copy()

    return interpreter.start(setup_file, config_objects_names, input_queue, output_queue, i)

