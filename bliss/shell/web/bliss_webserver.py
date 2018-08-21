# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import sys
import optparse
import gevent
import gevent.event
import gevent.queue
import gevent.monkey

gevent.monkey.patch_all()
import gipc
import bottle
import socket
import time
import logging
import cStringIO
import json
import signal
import uuid
from jinja2 import Template
import bliss.shell.interpreter as interpreter
from bliss.config import static as static_config
from bliss.config.conductor import client as beacon

EXECUTION_QUEUE = dict()
OUTPUT_QUEUE = dict()
INTERPRETER = dict()
RESULT = dict()
SESSION_INIT = dict()
SYNOPTIC = dict()

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
        try:
            client_uuid, output = q.get()
        except EOFError:
            break

        if client_uuid is None:
            # broadcast to all clients
            print "broadcast to all clients", output
            for client_uuid, per_client_queue in OUTPUT_QUEUE[session_id].iteritems():
                print "  - dispatching output to", client_uuid
                per_client_queue.put(output)
                gevent.sleep(0)
        elif "setup" in client_uuid:
            tag, client_uuid = client_uuid

            if isinstance(output, str):
                output = {"type": "setup", "data": output}

            OUTPUT_QUEUE[session_id][client_uuid].put(output)
        else:
            try:
                OUTPUT_QUEUE[session_id][client_uuid].put(output)
            except KeyError:
                continue


@bottle.route("/<session_id>/output_stream/<client_uuid>")
def send_output(session_id, client_uuid):
    bottle.response.content_type = "text/event-stream"
    bottle.response.add_header("Connection", "keep-alive")
    bottle.response.add_header("Cache-control", "no-cache, must-revalidate")

    if OUTPUT_QUEUE.get(session_id) is None:
        # browser tries to (re)connect but we don't know this session
        bottle.response.status = 404
        raise StopIteration

    q = OUTPUT_QUEUE[session_id][client_uuid]

    # this is to initialize connection, something has to be sent
    yield "data: \n\n"

    while True:
        output = q.get()

        if output:
            if isinstance(output, StopIteration):
                RESULT[session_id][client_uuid].set(output.args[0])
            elif isinstance(output, str):
                yield "data: " + json.dumps(
                    {"type": "output", "data": {"type": "text", "data": output}}
                ) + "\n\n"
            elif isinstance(output, dict):
                if "scan_id" in output:
                    yield "data: " + json.dumps(
                        {"type": "output", "data": {"type": "plot", "data": output}}
                    ) + "\n\n"
                elif output.get("type") == "setup":
                    yield "data: " + json.dumps(
                        {"type": "output", "data": output}
                    ) + "\n\n"
                elif output.get("type") == "log":
                    yield "data: " + json.dumps(
                        {"type": "output", "data": output}
                    ) + "\n\n"
                else:
                    yield "data: " + json.dumps(
                        {"type": "synoptic", "data": output}
                    ) + "\n\n"
            else:
                continue


@bottle.route("/<session_id>/synoptic/run/<object_name>/<method_name>")
def action_from_synoptic(session_id, object_name, method_name):
    EXECUTION_QUEUE[session_id].put((None, "synoptic", (object_name, method_name)))


# @bottle.route("/log_msg_request")
# def send_log():
#    session_id = bottle.request.GET["session_id"]
#    return json.dumps(MyLogHandler(session_id).queue.get())


def interpreter_exec(session_id, client_uuid, action, *args):
    print "in interpreter_exec:", action, args
    res = gevent.event.AsyncResult()
    if isinstance(client_uuid, tuple):
        tag, uuid = client_uuid
    else:
        uuid = client_uuid

    RESULT[session_id][uuid] = res
    EXECUTION_QUEUE[session_id].put((client_uuid, action, args))
    return res.get()


@bottle.get("/<session_id>/completion_request")
def send_completion(session_id):
    client_uuid = bottle.request.GET["client_uuid"]
    text = bottle.request.GET["text"]
    completion_start_index = int(bottle.request.GET["index"])
    possibilities, completions = interpreter_exec(
        session_id, client_uuid, "complete", text, completion_start_index
    )
    return {"possibilities": possibilities, "completions": completions}


@bottle.get("/<session_id>/abort")
def abort_execution(session_id):
    os.kill(INTERPRETER[session_id].pid, signal.SIGINT)


@bottle.get("/<session_id>/command")
def execute_command(session_id):
    client_uuid = bottle.request.GET["client_uuid"]
    code = bottle.request.GET["code"]
    if not code:
        return {"error": ""}

    return _execute_command(session_id, client_uuid, code)


def _execute_command(session_id, client_uuid, code):
    try:
        python_code_to_execute = str(code).strip() + "\n"
    except UnicodeEncodeError, err_msg:
        return {"error": str(err_msg)}
    else:
        res = interpreter_exec(
            session_id, client_uuid, "execute", python_code_to_execute
        )
        if isinstance(res, EOFError):
            return {"error": "EOF", "input": python_code_to_execute}
        elif isinstance(res, RuntimeError):
            error_string = str(res)
            sys.stderr.write(error_string)
            return {"error": error_string + "\n"}
        else:
            return {"error": ""}


@bottle.get("/<session_id>/args_request")
def get_func_args(session_id):
    client_id = bottle.request.GET["client_uuid"]
    code = bottle.request.GET["code"]
    return interpreter_exec(session_id, client_id, "get_function_args", str(code))


@bottle.route("/<session_id>/setup")
def setup(session_id):
    client_uuid = bottle.request.GET["client_uuid"]
    force = bottle.request.GET["force"] == "true"

    if force or SESSION_INIT.get(session_id) is None:
        SESSION_INIT[session_id] = True
        return _execute_command(session_id, ("setup", client_uuid), "resetup()\n")
    else:
        return {"error": ""}


@bottle.route("/<session_id>")
def open_session(session_id):
    client_id = str(uuid.uuid1())

    if not session_id in INTERPRETER:
        cmds_queue, EXECUTION_QUEUE[session_id] = gipc.pipe()
        output_queue_from_interpreter, output_queue = gipc.pipe()
        RESULT[session_id] = dict()

        config = static_config.get_config()
        session = config.get(session_id)
        session_cfg = config.get_config(session.name)
        synoptic = session_cfg.get("synoptic")
        if synoptic:
            SYNOPTIC[session_id] = synoptic

        INTERPRETER[session_id] = gipc.start_process(
            interpreter.start_interpreter,
            args=(session_id, cmds_queue, output_queue),
            kwargs={
                "beacon_host": os.environ.get("BEACON_HOST"),
                "beacon_port": os.environ.get("BEACON_PORT"),
            },
        )
        EXECUTION_QUEUE[session_id].put((None, "syn", (None,)))
        output_queue_from_interpreter.get()  # ack

        OUTPUT_QUEUE[session_id] = dict()
        gevent.spawn(handle_output, session_id, output_queue_from_interpreter)

    RESULT[session_id][client_id] = gevent.event.AsyncResult()
    OUTPUT_QUEUE[session_id][client_id] = gevent.queue.Queue()

    root_path = os.path.dirname(os.path.abspath(__file__))
    contents = file(os.path.join(root_path, "shell.html"), "r")
    template = Template(contents.read())
    return template.render(client_uuid=repr(client_id))


# @bottle.route("/<session_id>/objects")
# def return_objects_names(session_id):
#    client_uuid = bottle.request.GET["client_uuid"]
#
#    return interpreter_exec(session_id, client_uuid, "get_objects", None)


@bottle.route("/<session_id>/synoptic")
def return_synoptic_svg(session_id):
    s = static_config.get_config().get(session_id)
    svg = SYNOPTIC.get(session_id, {}).get("svg-file")
    if svg:
        return beacon.get_config_file(s.synoptic_file)
    else:
        return ""


@bottle.route("/<session_id>/synoptic/objects")
def return_synoptic_objects(session_id):
    if not session_id in SYNOPTIC:
        return {}

    client_uuid = bottle.request.GET["client_uuid"]
    objects = dict()

    elements = SYNOPTIC[session_id]["elements"]

    for elt in elements:
        d = {"top": [], "bottom": []}
        objects[elt["svg-id"]] = d
        for x in ("top", "bottom"):
            xx = elt.get(x, "")
            if xx:
                for obj_name in xx.split():
                    obj = interpreter_exec(
                        session_id, client_uuid, "get_object", obj_name
                    )
                    obj["name"] = obj_name
                    d[x].append(obj)
    print objects
    return objects


@bottle.route("/sessions")
def sessions_list():
    config = static_config.get_config()
    sessions = ["<ul>"]
    for name in config.names_list:
        c = config.get_config(name)
        if c.get("class") != "Session":
            continue
        if c.get_inherited("plugin") != "session":
            continue
        sessions.append("<li><a href='/%s'>%s</a></li>" % (name, name))
    sessions.append("</ul>")
    return (
        "<html><head><h3>BLISS sessions</h3><br></head><body>%s</body></html>"
        % "\n".join(sessions)
    )


@bottle.route("/")
def main():
    # redirect to default session or to list if there is no default
    config = static_config.get_config()
    for name in config.names_list:
        c = config.get_config(name)
        if c.get("class") != "Session":
            continue
        if c.get_inherited("plugin") != "session":
            continue
        if c.get("default", False):
            bottle.redirect("/%s" % name)
    bottle.redirect("/sessions")


@bottle.route("/js/<url:path>")
def serve_static_file(url):
    return bottle.static_file(url, os.path.join(os.path.dirname(__file__), "js"))


@bottle.route("/css/<url:path>")
def serve_static_file(url):
    return bottle.static_file(url, os.path.join(os.path.dirname(__file__), "css"))


@bottle.route("/<url:path>")
def serve_static_file(url):
    return bottle.static_file(url, os.path.dirname(__file__))


def serve_forever(port=None):
    bottle.run(server="gevent", host="0.0.0.0", port=port)
