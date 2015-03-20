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
import logging
import functools
from contextlib import contextmanager
from bliss import SETUP_FILE, setup
from bliss.common.event import dispatcher
from bliss.common import data_manager
from bliss.common import measurement
#try:
#    from bliss.config import static as beacon_static
#except:
#    beacon_static = None
jedi.settings.case_insensitive_completion = False

class LogHandler(logging.Handler):

    def __init__(self, queue):
        logging.Handler.__init__(self)

        self.queue = queue

    def emit(self, record):
        self.queue.put((None, {"type":"log", "data": { "message": self.format(record), "level": record.levelname }}))
    

class Stdout:

    def __init__(self, queue):
        self.queue = queue
        self.client_uuid = None

    def flush(self):
        pass

    def write(self, output):
        self.queue.put((self.client_uuid, output))        


@contextmanager
def stdout_redirected(client_uuid, new_stdout):
    new_stdout.client_uuid = client_uuid
    save_stdout = sys.stdout
    sys.stdout = new_stdout
    try:
        yield None
    finally:
        sys.stdout = save_stdout


def init_scans_callbacks(interpreter, output_queue):
    def new_scan_callback(scan_id, filename, scan_actuators, npoints, counters_list):
        output_queue.put((interpreter.get_last_client_uuid(), {"scan_id": scan_id, "filename": filename,
                          "scan_actuators": scan_actuators, "npoints": npoints,
                          "counters": counters_list}))
    def update_scan_callback(scan_id, values):
        output_queue.put((interpreter.get_last_client_uuid(), {"scan_id": scan_id, "values":values}))
    def scan_end_callback(scan_id):
        output_queue.put((interpreter.get_last_client_uuid(), {"scan_id":scan_id}))

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

    def runcode(self, client_uuid, c):
        try:
            with stdout_redirected(client_uuid, self.output):
                exec c in self.locals
        except SystemExit:
            raise
        except KeyboardInterrupt:
            self.error.write("KeyboardInterrupt")
        except:
            self.showtraceback()

    def compile_and_run(self, client_uuid, python_code_to_execute):
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
                self.runcode(client_uuid, code_obj)
                
                if self.error.tell() > 0:
                    error_string = self.error.getvalue()
                    self.error = cStringIO.StringIO()
                    raise RuntimeError(error_string)

    def execute(self, client_uuid, python_code_to_execute, wait=True):
        self.executed_greenlet = gevent.spawn(self.compile_and_run, client_uuid, python_code_to_execute)
        self.executed_greenlet.client_uuid = client_uuid
        if wait:
            return self.executed_greenlet.get()
        else:
            gevent.sleep(0)
            return self.executed_greenlet

    def get_last_client_uuid(self):
        if self.executed_greenlet and not self.executed_greenlet.ready():
            return self.executed_greenlet.client_uuid
        

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
        if has_method(obj, all, "move", "state", "position"):
            motors[name]=obj

        # is it a counter?
        if isinstance(obj, measurement.CounterBase):
            counters[name]=obj
        else:
            if not inspect.ismodule(obj):
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
                has_method(obj, any, "set_in") and \
                has_method(obj, any, "set_out"):
            inout[name]=obj
        if not inspect.ismodule(obj):
            for member_name, member in inspect.getmembers(obj):
                if isinstance(getattr(obj.__class__, member_name, None), property):
                    if has_method(member, all, "state") and \
                            has_method(member, any, "set_in") and \
                            has_method(member, any, "set_out"):
                        inout["%s.%s" % (name, member_name)]=member

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
    init_scans_callbacks(i, output_queue)

    i.locals["resetup"] = functools.partial(setup, env_dict=i.locals)
    i.locals["SETUP_FILE"] = SETUP_FILE

    root_logger = logging.getLogger()
    custom_log_handler = LogHandler(output_queue) 
    custom_log_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    root_logger.addHandler(custom_log_handler)
 
    while True:
        client_uuid, action, _ = input_queue.get()
        if action == "syn":
            output_queue.put("ack")
            continue
        elif action == "control_panel":
            object_name, method_name = _
            namespace = i.locals
            for name in object_name.split('.'):
                obj = namespace.get(name)
                namespace = dict(inspect.getmembers(obj))
            if obj is not None:
                method = getattr(obj, method_name)
                if callable(method):
                    gevent.spawn(method)
        elif action == "get_objects":
            objects_by_type = get_objects_by_type(i.locals)
            pprint.pprint(objects_by_type)

            motors_list = list()
            for name, m in objects_by_type["motors"].iteritems():
		try:
		    pos = "%.3f" % m.position()
		    state = convert_state(m.state())
		except:
		    pos = None
		    state = None
                motors_list.append({ "name": m.name, "state": state, "position": pos })
                def state_updated(state, name=name):
                    output_queue.put((None, { "name":name, "state": convert_state(state)}))
                def position_updated(pos, name=name, client_uuid=client_uuid):
                    pos = "%.3f" % pos
                    output_queue.put((None, {"name":name, "position":pos}))
                output_queue.callbacks["motor"][name]=(state_updated, position_updated) 
                dispatcher.connect(state_updated, "state", m)
                dispatcher.connect(position_updated, "position", m)
            motors_list = sorted(motors_list, cmp=lambda x,y: cmp(x["name"],y["name"]))

            counters_list = list()
            for name, cnt in objects_by_type["counters"].iteritems():
                counters_list.append({"name":name})

            inout_list = list()
            for name, obj in objects_by_type["inout"].iteritems():
		try:
		    state = obj.state()
		except:
		    state = None
                inout_list.append({"name": name, "state": convert_state(state)})
                def state_updated(state, name=name):
                    output_queue.put((None, {"name": name, "state": convert_state(state)}))
                output_queue.callbacks["inout"][name]=state_updated
                dispatcher.connect(state_updated, "state", obj)
            inout_list = sorted(inout_list, cmp=lambda x,y: cmp(x["name"],y["name"]))
  
            openclose_list = list()
            for name, obj in objects_by_type["openclose"].iteritems():
		try:
		    state = obj.state()
		except:
		    state = None
		openclose_list.append({"name": name, "state": convert_state(state) })
		def state_updated(state, name=name):
		    output_queue.put((None, {"name":name, "state":convert_state(state)}))
		output_queue.callbacks["openclose"][name]=state_updated
		dispatcher.connect(state_updated, "state", obj)
	    openclose_list = sorted(openclose_list, cmp=lambda x,y: cmp(x["name"],y["name"]))

            output_queue.put((None, StopIteration({ "motors": motors_list, "counters": counters_list, "inout": inout_list, "openclose": openclose_list })))
        elif action == "execute":
            code = _[0]

            if client_uuid is not None:
                if i.executed_greenlet and not i.executed_greenlet.ready():
                     output_queue.put((client_uuid, StopIteration(RuntimeError("Server is busy."))))
                     continue

            def execution_done(executed_greenlet, output_queue=output_queue, client_uuid=client_uuid):
                try:
                    res = executed_greenlet.get()
                except EOFError:
                    output_queue.put((client_uuid, StopIteration(EOFError())))
                except RuntimeError, error_string: 
                    output_queue.put((client_uuid, StopIteration(RuntimeError(error_string))))
                else:
                    output_queue.put((client_uuid, StopIteration(None)))

            i.execute(client_uuid, code, wait=False).link(execution_done)
        elif action == "complete":
            text, completion_start_index = _
            completion_obj = jedi.Interpreter(text, [i.locals], line=1, column=completion_start_index)
            possibilities = []
            completions = []
            for x in completion_obj.completions():
                possibilities.append(x.name)
                completions.append(x.complete)
            output_queue.put((client_uuid, StopIteration((possibilities, completions))))
        elif action == "get_function_args":
            code = _[0]
            try:
                ast_node = ast.parse(code)
            except:
                output_queue.put((client_uuid, StopIteration({"func": False})))
            else:
                if isinstance(ast_node.body[-1], ast.Expr):
                    expr = code[ast_node.body[-1].col_offset:]
                    try:
                        x = eval(expr, i.locals)
                    except:
                        output_queue.put((client_uuid, StopIteration({"func": False})))
                    else:
                        if callable(x):
                            try:
                              if inspect.isfunction(x):
                                  args = inspect.formatargspec(*inspect.getargspec(x))
                              elif inspect.ismethod(x):
                                  argspec = inspect.getargspec(x)
                                  args = inspect.formatargspec(argspec.args[1:],*argspec[1:])
                              else:
                                  raise TypeError
                            except TypeError:
                              output_queue.put((client_uuid, StopIteration({"func": False})))
                            else:
                              output_queue.put((client_uuid, StopIteration({"func": True, "func_name":expr, "args": args })))
                        else:
                            output_queue.put((client_uuid, StopIteration({"func": False})))

