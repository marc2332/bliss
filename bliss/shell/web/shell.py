import os
import re
import sys
import optparse
import gevent
import gevent.queue
import gevent.event
import gevent.monkey
import bottle
import socket
import time
import logging
import code
import jedi
import cStringIO
import json
#import redis
import inspect
from bliss.common.event import **
from bliss.common import data_manager
from bliss.common import scans
from bliss.common import task_utils

LOG = {}
OUTPUT = {}
CODE_EXECUTION = {}
ROOT_PATH = os.path.dirname(os.path.abspath(__file__))
INTERPRETER = None
INTERPRETER_GLOBALS = {}
NEW_SCAN = gevent.event.AsyncResult()

#add scan and task functions
for module in (scans, task_utils):
    INTERPRETER_GLOBALS.update(dict([(x,y) for x,y in module.__dict__.iteritems() if inspect.isfunction(y)]))

class GreenletStdout:
  def write(self, output):
    # find right client id depending on greenlet
    for session_id, greenlet in CODE_EXECUTION.iteritems():
      if greenlet == gevent.getcurrent():
        break
    else:
        return

    OUTPUT[session_id].put(output)

# patch socket module;
# by default bottle doesn't set address as reusable
# and there is no option to do it...
socket.socket._bind = socket.socket.bind
def my_socket_bind(self, *args, **kwargs):
  self.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
  return socket.socket._bind(self, *args, **kwargs)
socket.socket.bind = my_socket_bind

"""
def scan_listener(redis_host, redis_port):
  r = redis.StrictRedis(host=redis_host, port=redis_port, db=0)
  p = r.pubsub()
  p.psubscribe("khoros.scans.*")
  while True:
      for new_scan in p.listen():
          print "<<<<NEW MSG FROM REDIS>>>>",new_scan
          NEW_SCAN.set(new_scan)
"""

class InteractiveInterpreter(code.InteractiveInterpreter):
  def __init__(self, globals_dict=None):
    if globals_dict is None:
      globals_dict = INTERPRETER_GLOBALS #globals()
    code.InteractiveInterpreter.__init__(self, globals_dict)

    self.at_prompt = True
    self.error = cStringIO.StringIO()

  def write(self, data):
    self.error.write(data)

  def runcode(self, c):
    try:
      exec c in self.locals
    except KeyboardInterrupt:
      self.showtraceback()
    except SystemExit:
      raise
    except:
      self.showtraceback()

  def compile_and_run(self, python_code_to_execute, dontcompile=False):
    code_obj = None
    self.at_prompt = False

    try:
      if dontcompile:
        self.runcode(python_code_to_execute)
      else:
        try:
          code_obj = code.compile_command(python_code_to_execute)
        except SyntaxError, exc_instance:
          raise RuntimeError, str(exc_instance)
        else:
          if code_obj is None:
            # input is incomplete
            raise EOFError
          else:
            self.runcode(code_obj)

            if self.error.tell() > 0:
              error_string = self.error.getvalue()
              self.error = cStringIO.StringIO()
              raise RuntimeError, error_string
    finally:
      self.at_prompt = True

def MyLogHandler(session_id):
  try:
    log_handler = LOG[session_id]
  except KeyError:
    log_handler = _MyLogHandler()
    log_handler.setLevel(logging.DEBUG)
    logging.getLogger().addHandler(log_handler)
    LOG[session_id]=log_handler

  return log_handler
  
class _MyLogHandler(logging.Handler):
  def __init__(self):
    logging.Handler.__init__(self)
    self.queue = gevent.queue.Queue() 
    
  def emit(self, record):
    self.queue.put(record.getMessage()) 

@bottle.route("/output_stream/<session_id>")
def send_output(session_id):
  bottle.response.content_type = 'text/event-stream'
  bottle.response.add_header("Connection", "keep-alive")
  bottle.response.add_header("Cache-control", "no-cache, must-revalidate")
  output = ""

  while True:
    try:
      output += OUTPUT[session_id].get(timeout=0.05)
    except KeyError:
      # an old client was waiting for us
      OUTPUT.setdefault(session_id, gevent.queue.Queue())
      yield "data: \n\n"
      continue
    except gevent.queue.Empty:
      if output:
        yield "data: "+json.dumps(output)+"\n\n"
        output = ""
    else:
      if not output.endswith("\n"):
        continue
      output.strip();
      #print "yielding", json.dumps(output)
      yield "data: "+json.dumps(output)+"\n\n"
      output = ""
      
@bottle.route("/log_msg_request")
def send_log():
  session_id = bottle.request.GET["session_id"]
  return json.dumps(MyLogHandler(session_id).queue.get())

@bottle.get("/completion_request")
def send_completion():
  text = bottle.request.GET["text"]
  completion_start_index = int(bottle.request.GET["index"])
  completion_obj = jedi.Interpreter(text, [INTERPRETER.locals], line=1, column=completion_start_index)
  completions = completion_obj.completions()
  return json.dumps({ "possibilities": [x.name for x in completions], "completions": [x.complete for x in completions] })

@bottle.get("/abort/<session_id>")
def abort_execution(session_id):
  CODE_EXECUTION[session_id].kill(exception=KeyboardInterrupt, block=True)
 
@bottle.get("/command/<session_id>")
def execute_command(session_id):
  code = bottle.request.GET["code"]
  output_queue = OUTPUT[session_id]

  try:
    python_code_to_execute = str(code).strip()+"\n"
  except UnicodeEncodeError: 
    python_code_to_execute = ""

  if len(python_code_to_execute) == 0:
    return json.dumps({"error":""})
  else:
    CODE_EXECUTION[session_id] = gevent.spawn(do_execute, python_code_to_execute) 
    res = CODE_EXECUTION[session_id].get()
    return json.dumps(res)

def do_execute(python_code_to_execute):
  try:
      sys.stdout = GreenletStdout()
      try:
        INTERPRETER.compile_and_run(python_code_to_execute)
      except EOFError:
        return {"error":"EOF","input":python_code_to_execute}
      except RuntimeError, e:
        error_string = str(e)
        sys.stderr.write(error_string)
        return {"error":error_string+"\n"}
      else:
        return {"error":""}
  finally:
      sys.stdout = sys.__stdout__ 

@bottle.route('/session')
def return_session_id(session={"id": 0}):
  session["id"]+=1;
  return json.dumps({ "session_id": session["id"] });

@bottle.route('/')
def main():
  contents = file(os.path.join(ROOT_PATH, "shell.html"), "r")
  return contents.read()

@bottle.route("/<url:path>")
def serve_static_file(url):
  return bottle.static_file(url, os.path.dirname(__file__))

def new_scan_callback(scan_id, filename, *args):
  NEW_SCAN.set(scan_id)

def serve_forever(port=None): #, redis="localhost:6379"):
  gevent.monkey.patch_all()

  dispatcher.connect(new_scan_callback, "scan_new", data_manager.DataManager())

  #redis_host, redis_port = redis.split(":")
  #gevent.spawn(scan_listener, redis_host, int(redis_port))
  bottle.run(server="gevent", host="0.0.0.0", port=port)
  

def set_interpreter(interpreter_object):
  global INTERPRETER
  INTERPRETER = interpreter_object


if __name__=="__main__":
    usage = "usage: \%prog [-p<port>] [-r<redis host:port>]"
    
    parser = optparse.OptionParser(usage)
    parser.add_option('-p', '--port', dest='port', type='int',
                      help='Port to listen on (default 8099)', default=8099, action='store')
    #parser.add_option('-r', '--redis', dest='redis', type='string',
    #                  help='Redis server and port number (default localhost:6379)', default="localhost:6379", action='store')
    
    options, args = parser.parse_args()

    logging.basicConfig()
    logging.getLogger().setLevel(logging.DEBUG)

    set_interpreter(InteractiveInterpreter())
    serve_forever(options.port) #, options.redis)
    
