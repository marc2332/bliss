import os
import sys
import ast
import inspect
import time
import logging
import code
import jedi
import cStringIO
import inspect
import pprint
import signal
import thread
import gevent
from contextlib import contextmanager
from bliss.common.event import dispatcher
from bliss.common import data_manager
from bliss.common import measurement
#try:
#    from bliss.config import static as beacon_static
#except:
#    beacon_static = None
jedi.settings.case_insensitive_completion = False

class Stdout:

    def __init__(self, queue):
        self.queue = queue

    def flush(self):
        pass

    def write(self, output):
        self.queue.put(output)        


@contextmanager
def stdout_redirected(new_stdout):
    save_stdout = sys.stdout
    sys.stdout = new_stdout
    try:
        yield None
    finally:
        sys.stdout = save_stdout


def init_scans_callbacks(output_queue):
    def new_scan_callback(scan_id, filename, scan_actuators, npoints, counters_list):
        output_queue.put({"scan_id": scan_id, "filename": filename,
                          "scan_actuators": scan_actuators, "npoints": npoints,
                          "counters": counters_list})
    def update_scan_callback(scan_id, values):
        output_queue.put({"scan_id": scan_id, "values":values})
    def scan_end_callback(scan_id):
        output_queue.put({"scan_id":scan_id})

    # keep callbacks references
    output_queue.callbacks["scans"]["new"] = new_scan_callback
    output_queue.callbacks["scans"]["update"] = update_scan_callback
    output_queue.callbacks["scans"]["end"] = scan_end_callback

    dispatcher.connect(
        new_scan_callback, "scan_new", data_manager.DataManager())
    dispatcher.connect(
        update_scan_callback, "scan_data", data_manager.DataManager())
    dispatcher.connect(
        scan_end_callback, "scan_end", data_manager.DataManager())


class InteractiveInterpreter(code.InteractiveInterpreter):

    def __init__(self, output_queue):
        code.InteractiveInterpreter.__init__(self) #, globals_dict)

        self.error = cStringIO.StringIO()
        self.output = Stdout(output_queue)
        self.executed_greenlet = None

    def write(self, data):
        self.error.write(data)

    def kill(self, exception):
        if self.executed_greenlet and not self.executed_greenlet.ready():
            self.executed_greenlet.kill(exception)
            return True
        return False

    def runcode(self, c):
        try:
            with stdout_redirected(self.output):
                exec c in self.locals
        except SystemExit:
            raise
        except KeyboardInterrupt:
            self.error.write("KeyboardInterrupt")
        except:
            self.showtraceback()

    def compile_and_run(self, python_code_to_execute):
        code_obj = None

        try:
            code_obj = code.compile_command(python_code_to_execute)
        except SyntaxError, exc_instance:
            raise RuntimeError(str(exc_instance))
        else:
            if code_obj is None:
                # input is incomplete
                raise EOFError
            else:
                self.runcode(code_obj)
                
                if self.error.tell() > 0:
                    error_string = self.error.getvalue()
                    self.error = cStringIO.StringIO()
                    raise RuntimeError(error_string)

    def execute(self, python_code_to_execute):
        self.executed_greenlet = gevent.spawn(self.compile_and_run, python_code_to_execute)
        return self.executed_greenlet.get()


def init(input_queue, output_queue):
    # undo thread module monkey-patching
    reload(thread)

    i = InteractiveInterpreter(output_queue)

    return i

def convert_state(state):
    if state is None:
        return "UNKNOWN"
    # in case of emotion state, state is *not* a string,
    # but comparison works like with a string
    if state == "MOVING":  
        return "MOVING"
    elif state == "HOME":
        return "HOME"
    elif state == "LIMPOS":
        return "ONLIMIT"
    elif state == "LIMNEG":
        return "ONLIMIT"
    elif state == "FAULT":
        return "FAULT"
    elif state == "READY":
        return "READY"
    else:
        if isinstance(state, str):
            return state.upper()
        else:
            return "UNKNOWN"

def has_method(obj, all_or_any, *method_names):
    return all_or_any((inspect.ismethod(getattr(obj, m, None)) for m in method_names))

def get_objects_by_type(objects_dict):
    motors = dict()
    counters = dict()
    inout = dict()
    openclose = dict()

    #if beacon_static:
    #    cfg = beacon_static.get_config()
    #else:
    #    cfg = None

    for name, obj in objects_dict.iteritems():
        if inspect.isclass(obj):
            continue
        # is it a motor?
        #if cfg:
        #    cfg_node = cfg.get_config(name)
        #    if cfg_node.plugin == 'emotion':
        #        motors.append(name)
        #        continue
        if has_method(obj, all, "move", "state", "position"):
            motors[name]=obj

        # is it a counter?
        if isinstance(obj, measurement.CounterBase):
            counters[name]=obj
        else:
            #if inspect.ismethod(getattr(obj, "read")):
            #    counters[name]=obj 
            try:
                obj_dict = obj.__dict__
            except AttributeError:
                pass
            else:
                for member_name, member in obj_dict.iteritems():
                    if isinstance(member, measurement.CounterBase):
                        counters["%s.%s" % (name, member_name)]=member
        
        # has it in/out capability?
        if has_method(obj, all, "state") and \
                has_method(obj, any, "set_in", "in") and \
                has_method(obj, any, "set_out", "out"):
            inout[name]=obj

        # has it open/close capability?
        if has_method(obj, all, "open", "close", "state"):
            openclose[name]=obj

    return { "motors": motors, "counters": counters, "inout": inout, "openclose": openclose }

def start(input_queue, output_queue, i):
    # restore default SIGINT behaviour
    def raise_kb_interrupt(interpreter=i):
        if not interpreter.kill(KeyboardInterrupt):
            raise KeyboardInterrupt
    gevent.signal(signal.SIGINT, raise_kb_interrupt)

    output_queue.callbacks = { "motor": dict(),
                               "scans": dict(),
                               "inout": dict(),
                               "openclose": dict() }
    init_scans_callbacks(output_queue)

    def resetup(setup_file=None):
        setup_file = i.locals.get("SETUP_FILE") if setup_file is None else setup_file
        if setup_file is not None:
            i.locals["SETUP_FILE"] = setup_file
            setup_file_path = os.path.abspath(os.path.expanduser(setup_file))
            if os.path.isfile(setup_file_path):
                setup_file_dir = os.path.dirname(setup_file_path)
                if not setup_file_dir in sys.path:
                    sys.path.insert(0, setup_file_dir)
                execfile(setup_file_path, i.locals)
    i.locals["resetup"] = resetup

    while True:
        action, _ = input_queue.get()
        if action == "syn":
            output_queue.put("ack")
            continue
        elif action == "objects_list":
            objects_by_type = get_objects_by_type(i.locals)
            pprint.pprint(objects_by_type)

            motors_list = list()
            for name, m in objects_by_type["motors"].iteritems():
                pos = "%.3f" % m.position()
                state = convert_state(m.state())
                motors_list.append({ "name": m.name, "state": state, "pos": pos })
                def state_updated(state, name=name):
                    output_queue.put({"name":name, "state": convert_state(state)})
                def position_updated(pos, name=name):
                    pos = "%.3f" % pos
                    output_queue.put({"name":name, "position":pos})
                output_queue.callbacks["motor"][name]=(state_updated, position_updated) 
                dispatcher.connect(state_updated, "state", m)
                dispatcher.connect(position_updated, "position", m)
            motors_list = sorted(motors_list, cmp=lambda x,y: cmp(x["name"],y["name"]))

            counters_list = list()
            for name, cnt in objects_by_type["counters"].iteritems():
                counters_list.append({"name":name})

            inout_list = list()
            for name, obj in objects_by_type["inout"].iteritems():
                state = obj.state()
                inout_list.append({"name": name, "state": convert_state(state)})
                def state_updated(state, name=name):
                    output_queue.put({"name": name, "state": convert_state(state)})
                output_queue.callbacks["inout"][name]=state_updated
                dispatcher.connect(state_updated, "state", obj)
            inout_list = sorted(inout_list, cmp=lambda x,y: cmp(x["name"],y["name"]))
  
            openclose_list = list()
            for name, obj in objects_by_type["openclose"].iteritems():
                openclose_list.append({"name": name})

            output_queue.put(StopIteration({ "motors": motors_list, "counters": counters_list, "inout": inout_list, "openclose": openclose_list }))
        elif action == "execute":
            code = _[0]
            try:
                i.execute(code)
            except EOFError:
                output_queue.put(StopIteration(EOFError()))
            except RuntimeError, error_string:
                print error_string
                output_queue.put(StopIteration(RuntimeError(error_string)))
            else:           
                output_queue.put(StopIteration(None))
        elif action == "complete":
            text, completion_start_index = _
            completion_obj = jedi.Interpreter(text, [i.locals], line=1, column=completion_start_index)
            possibilities = []
            completions = []
            for x in completion_obj.completions():
                possibilities.append(x.name)
                completions.append(x.complete)
            output_queue.put(StopIteration((possibilities, completions)))
        elif action == "get_function_args":
            code = _[0]
            try:
                ast_node = ast.parse(code)
            except:
                output_queue.put(StopIteration({"func": False}))
            else:
                if isinstance(ast_node.body[-1], ast.Expr):
                    expr = code[ast_node.body[-1].col_offset:]
                    try:
                        x = eval(expr, i.locals)
                    except:
                        output_queue.put(StopIteration({"func": False}))
                    else:
                        if callable(x):
                            try:
                                x.__call__
                            except AttributeError:
                                if inspect.isfunction(x):
                                    args = inspect.formatargspec(*inspect.getargspec(x))
                                elif inspect.ismethod(x):
                                    argspec = inspect.getargspec(x)
                                    args = inspect.formatargspec(argspec.args[1:],*argspec[1:])
                                else:
                                    output_queue.put(StopIteration({"func": False}))
                                    continue
                                output_queue.put(StopIteration({"func": True, "func_name":expr, "args": args }))
                            else:
                                output_queue.put(StopIteration({"func": False}))
                                continue
                                # like a method
                                #argspec = inspect.getargspec(x.__call__)
                                #args = inspect.formatargspec(argspec.args[1:],*argspec[1:])
                        else:
                            output_queue.put(StopIteration({"func": False}))

