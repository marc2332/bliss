from types import ModuleType
import sys

def start_interpreter(setup_file, input_queue, output_queue):
    interpreter = __import__("interpreter", globals(), locals(), [])

    i = interpreter.init(input_queue, output_queue)
  
    globals_module = ModuleType("globals")
    sys.modules["khoros.interpreter"].globals = globals_module
    sys.modules["khoros.interpreter.globals"] = globals_module 

    i.locals = globals_module.__dict__

    return interpreter.start(setup_file, input_queue, output_queue, i)

