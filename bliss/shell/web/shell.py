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
import uuid
from jinja2 import Template

#LOG = {}
EXECUTION_QUEUE = dict()
OUTPUT_QUEUE = dict()
CONTROL_PANEL_QUEUE = dict()
INTERPRETER = dict()
RESULT = dict()
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


def handle_output(session_id, q):
    while True:
        client_uuid, output = q.get()
        
        if client_uuid is None:
            # broadcast to all clients
            for client_uuid, per_client_queue in OUTPUT_QUEUE[session_id].iteritems():
                print "dispatching output to", client_uuid
                per_client_queue.put(output)
        else:
            try:
                OUTPUT_QUEUE[session_id][client_uuid].put(output)
            except KeyError:
                continue


@bottle.route("/<session_id:int>/output_stream/<client_uuid>")
def send_output(session_id, client_uuid):
    bottle.response.content_type = 'text/event-stream'
    bottle.response.add_header("Connection", "keep-alive")
    bottle.response.add_header("Cache-control", "no-cache, must-revalidate")
    output_text = ""

    if OUTPUT_QUEUE.get(session_id) is None:
        # browser tries to (re)connect but we don't know this session
        bottle.response.status = 404
        raise StopIteration

    q = OUTPUT_QUEUE[session_id][client_uuid]
    
    # this is to initialize connection, something has to be sent
    yield "data: \n\n"

    while True:
        #output = None
        #with gevent.Timeout(0.05, False) as t:
        #    output = OUTPUT_QUEUE[session_id].get(timeout=t)
        output = q.get()        

        if output:
            if isinstance(output, StopIteration):
                RESULT[session_id][client_uuid].set(output.args[0])
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
            #if not output_text.endswith("\n"):
            #    continue
            yield "data: " + json.dumps({"type": "text", "data": output_text }) + "\n\n"
            output_text = ""


@bottle.route("/<session_id:int>/control_panel_events/<client_uuid>")
def send_control_panel_events(session_id, client_uuid):
    bottle.response.content_type = 'text/event-stream'
    bottle.response.add_header("Connection", "keep-alive")
    bottle.response.add_header("Cache-control", "no-cache, must-revalidate")

    if CONTROL_PANEL_QUEUE.get(session_id) is None:
        # browser tries to (re)connect but we don't know this session
        bottle.response.status = 404
        raise StopIteration

    q = CONTROL_PANEL_QUEUE[session_id][client_uuid]

    # this is to initialize connection, something has to be sent
    yield "data: \n\n"
    
    while True:
        data = q.get()
        yield "data: " + json.dumps({"type": "control_panel_motor", "data":data}) + "\n\n"

@bottle.route("/<session_id:int>/control_panel/run/<object_name>/<method_name>")
def action_from_control_panel(session_id, object_name, method_name):
    EXECUTION_QUEUE[session_id].put((None, "control_panel", (object_name, method_name)))   


#@bottle.route("/log_msg_request")
#def send_log():
#    session_id = bottle.request.GET["session_id"]
#    return json.dumps(MyLogHandler(session_id).queue.get())


def execute_cmd(session_id, client_uuid, action, *args):
    print 'in execute_cmd:', action, args
    res = gevent.event.AsyncResult()
    res.client_uuid = client_uuid
    RESULT[session_id][client_uuid] = res
    EXECUTION_QUEUE[session_id].put((client_uuid, action, args))
    return res.get()


@bottle.get("/<session_id:int>/completion_request")
def send_completion(session_id):
    client_uuid = bottle.request.GET["client_uuid"]
    text = bottle.request.GET["text"]
    completion_start_index = int(bottle.request.GET["index"])
    possibilities, completions = execute_cmd(session_id, client_uuid, "complete", text, completion_start_index)
    return {"possibilities": possibilities,
            "completions": completions }


@bottle.get("/<session_id:int>/abort")
def abort_execution(session_id):
    os.kill(INTERPRETER[session_id].pid, signal.SIGINT)


@bottle.get("/<session_id:int>/command")
def execute_command(session_id):
    client_uuid = bottle.request.GET["client_uuid"]
    code = bottle.request.GET["code"]
    if not code:
        return {"error": ""}

    return _execute_command(code, client_uuid, session_id)


def _execute_command(code, client_uuid, session_id):
    try:
        python_code_to_execute = str(code).strip() + "\n"
    except UnicodeEncodeError, err_msg:
        return {"error": str(err_msg)}
    else:
        res = execute_cmd(session_id, client_uuid, "execute", python_code_to_execute)
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
    client_id = bottle.request.GET["client_uuid"]
    code = bottle.request.GET["code"]
    return execute_cmd(session_id, client_id, "get_function_args", str(code))
    

@bottle.route('/<session_id:int>/setup')
def setup(session_id):
    client_uuid = bottle.request.GET["client_uuid"]
    force = bottle.request.GET["force"]

    if force or SESSION_INIT.get(session_id) is None:
        SESSION_INIT[session_id] = True
        return _execute_command("resetup()\n", client_uuid, session_id)
    else:
        return {"error":""}
	

@bottle.route('/<session_id:int>')
def open_session(session_id):
    client_id = str(uuid.uuid1())

    if not session_id in INTERPRETER:
        cmds_queue,EXECUTION_QUEUE[session_id] = gipc.pipe()
        output_queue_from_interpreter, output_queue = gipc.pipe()
        RESULT[session_id] = dict()
        INTERPRETER[session_id] = gipc.start_process(interpreter.start_interpreter,
                                                     args=(cmds_queue, output_queue))
        EXECUTION_QUEUE[session_id].put((None, "syn", (None,)))
        output_queue_from_interpreter.get() #ack
    
        OUTPUT_QUEUE[session_id] = dict()
        CONTROL_PANEL_QUEUE[session_id] = dict()
        gevent.spawn(handle_output, session_id, output_queue_from_interpreter)
    
    RESULT[session_id][client_id] = gevent.event.AsyncResult()
    OUTPUT_QUEUE[session_id][client_id] = gevent.queue.Queue()
    RESULT[session_id]["setup_"+client_id] = gevent.event.AsyncResult()
    OUTPUT_QUEUE[session_id]["setup_"+client_id] = gevent.queue.Queue()
    CONTROL_PANEL_QUEUE[session_id][client_id] = gevent.queue.Queue()

    root_path = os.path.dirname(os.path.abspath(__file__))
    contents = file(os.path.join(root_path, "shell.html"), "r")
    template = Template(contents.read())
    return template.render(client_uuid=repr(client_id))


@bottle.route("/<session_id:int>/objects")
def return_objects_names(session_id):
    return execute_cmd(session_id, None, "get_objects", None)


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
