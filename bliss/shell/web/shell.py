import os
import sys
import optparse
import gevent
import gevent.event
import gevent.queue
import gevent.monkey
gevent.monkey.patch_all()
import bottle
import socket
import time
import logging
import cStringIO
import json
import bliss.shell.interpreter as interpreter
import gipc
import signal

#LOG = {}
GLOBALS = {}
EXECUTION_QUEUE = dict()
OUTPUT_QUEUE = dict()
CONTROL_PANEL_QUEUE = dict()
INTERPRETER = dict()
RESULT = dict()
OUTPUT_STREAM_READY = dict()
INIT_SCRIPT = ""
SESSION_INIT = dict()

# patch socket module;
# by default bottle doesn't set address as reusable
# and there is no option to do it...
socket.socket._bind = socket.socket.bind

def my_socket_bind(self, *args, **kwargs):
    self.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    return socket.socket._bind(self, *args, **kwargs)
socket.socket.bind = my_socket_bind


def set_globals(*globals_list): 
    global GLOBALS
    GLOBALS = globals_list


@bottle.route("/<session_id:int>/output_stream")
def send_output(session_id):
    bottle.response.content_type = 'text/event-stream'
    bottle.response.add_header("Connection", "keep-alive")
    bottle.response.add_header("Cache-control", "no-cache, must-revalidate")
    output_text = ""

    # this is to initialize connection, something has to be sent
    yield "data: \n\n" 
    OUTPUT_STREAM_READY[session_id].set()

    while True:
        output = None
        with gevent.Timeout(0.05, False) as t:
            output = OUTPUT_QUEUE[session_id].get(timeout=t)
        
        if output:
            if isinstance(output, StopIteration):
                RESULT[session_id].set(output.args[0])
                continue
            if isinstance(output, str):
                output_text += output
            elif isinstance(output, dict):
                if 'scan_id' in output:
                    yield "data: " + json.dumps({"type": "plot", "data": output}) + "\n\n"
                else:
                    CONTROL_PANEL_QUEUE[session_id].put(output)
                continue
            else:
                continue
            if not output_text.endswith("\n"):
                continue
            yield "data: " + json.dumps({"type": "text", "data": output_text }) + "\n\n"
            output_text = ""


@bottle.route("/<session_id:int>/control_panel_events")
def send_output(session_id):
    bottle.response.content_type = 'text/event-stream'
    bottle.response.add_header("Connection", "keep-alive")
    bottle.response.add_header("Cache-control", "no-cache, must-revalidate")

    # this is to initialize connection, something has to be sent
    yield "data: \n\n"
    
    while True:
        data = CONTROL_PANEL_QUEUE[session_id].get()
        yield "data: " + json.dumps({"type": "control_panel_motor", "data":data}) + "\n\n"


#@bottle.route("/log_msg_request")
#def send_log():
#    session_id = bottle.request.GET["session_id"]
#    return json.dumps(MyLogHandler(session_id).queue.get())


def execute_cmd(session_id, action, *args):
    OUTPUT_STREAM_READY[session_id].wait()
    RESULT[session_id] = gevent.event.AsyncResult()
    EXECUTION_QUEUE[session_id].put((action, args))
    return RESULT[session_id].get()


@bottle.get("/<session_id:int>/completion_request")
def send_completion(session_id):
    text = bottle.request.GET["text"]
    completion_start_index = int(bottle.request.GET["index"])
    possibilities, completions = execute_cmd(session_id, "complete", text, completion_start_index)
    return {"possibilities": possibilities,
            "completions": completions }


@bottle.get("/<session_id:int>/abort")
def abort_execution(session_id):
    os.kill(INTERPRETER[session_id].pid, signal.SIGINT)


@bottle.get("/<session_id:int>/command")
def execute_command(session_id):
    code = bottle.request.GET["code"]
    if code == "__INIT_SCRIPT__":
        if not SESSION_INIT.get(session_id):
            SESSION_INIT[session_id]=True
            code = INIT_SCRIPT
        else:
            code = ""

    try:
        python_code_to_execute = str(code).strip() + "\n"
    except UnicodeEncodeError, err_msg:
        return {"error": str(err_msg)}
    else:
        res = execute_cmd(session_id, "execute", python_code_to_execute)
        if isinstance(res, EOFError):
            return {"error": "EOF", "input": python_code_to_execute}
        elif isinstance(res, RuntimeError):
            error_string = str(res)
            sys.stderr.write(error_string)
            return {"error": error_string + "\n"}
        else:
            return {"error":""}


@bottle.get("/<session_id:int>/args_request")
def get_func_args(session_id):
    code = bottle.request.GET["code"]
    return execute_cmd(session_id, "get_function_args", str(code))
    

@bottle.route('/<session_id:int>')
def open_session(session_id):
    cmds_queue,EXECUTION_QUEUE[session_id] = gipc.pipe()
    OUTPUT_QUEUE[session_id], output_queue = gipc.pipe()
    CONTROL_PANEL_QUEUE[session_id]=gevent.queue.Queue()
    OUTPUT_STREAM_READY[session_id] = gevent.event.Event()
    RESULT[session_id]=gevent.event.AsyncResult()
    INTERPRETER[session_id] = gipc.start_process(interpreter.start_interpreter,
                                                 args=(cmds_queue, output_queue, GLOBALS))
    EXECUTION_QUEUE[session_id].put(("syn", (None,)))
    assert(OUTPUT_QUEUE[session_id].get() == "ack")
    
    root_path = os.path.dirname(os.path.abspath(__file__))
    contents = file(os.path.join(root_path, "shell.html"), "r")
    return contents.read()


@bottle.route("/<session_id:int>/motors_names")
def return_motors_names(session_id):
    motors_list = execute_cmd(session_id, "motors_list", None)
    print motors_list
    return { "motors": motors_list }


@bottle.route('/')
def main():
    bottle.redirect("/1")


@bottle.route("/<url:path>")
def serve_static_file(url):
    return bottle.static_file(url, os.path.dirname(__file__))


def set_init_script(script):
    global INIT_SCRIPT
    INIT_SCRIPT = script


def serve_forever(port=None):
    bottle.run(server="gevent", host="0.0.0.0", port=port)



if __name__ == "__main__":
    usage = "usage: \%prog [-p<port>]" #[-r<redis host:port>]"

    parser = optparse.OptionParser(usage)
    parser.add_option(
        '-p', '--port', dest='port', type='int',
        help='Port to listen on (default 8099)', default=8099, action='store')
    # parser.add_option('-r', '--redis', dest='redis', type='string',
    # help='Redis server and port number (default localhost:6379)',
    # default="localhost:6379", action='store')
    options, args = parser.parse_args()

    logging.basicConfig()
    logging.getLogger().setLevel(logging.DEBUG)

    serve_forever(options.port)  # , options.redis)
