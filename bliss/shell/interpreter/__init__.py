def start_interpreter(input_queue, output_queue, globals_list=None, init_script=""):
    interpreter = __import__("interpreter", globals(), locals(), [])
    return interpreter.start(input_queue, output_queue, globals_list, init_script)

