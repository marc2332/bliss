import os
import re
import sys
import optparse
import gevent
import gevent.queue
import gevent.monkey
import bottle
import socket
import time
import gevent
import logging
import code
import jedi
import traceback
import cStringIO
import json

HISTORY = {}
LOG = {}
OUTPUT = {}
CODE_EXECUTION = {}
ROOT_PATH = os.path.dirname(os.path.abspath(__file__))
INTERPRETER = None
INTERPRETER_GLOBALS = {}

def export(name, obj):
  INTERPRETER_GLOBALS[name]=obj

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

class InteractiveInterpreter(code.InteractiveInterpreter):
  def __init__(self, globals_dict=None):
    if globals_dict is None:
      globals_dict = INTERPRETER_GLOBALS #globals()
    code.InteractiveInterpreter.__init__(self, globals_dict)

    self.at_prompt = True
    #self.completer = rlcompleter.Completer(globals_dict)
    self.error = cStringIO.StringIO()

  def write(self, data):
    self.error.write(data)

  def runcode(self, c):
    try:
      exec c in self.locals
    except KeyboardInterrupt:
      self.showtraceback()
    except SystemExit:
      # maybe a self.showtraceback() would be good?
      raise
    except:
      self.showtraceback()
    else:
      if code.softspace(sys.stdout, 0):
         print

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

  while True:
    try:
      output = OUTPUT[session_id].get()
    except KeyError:
      # an old client was waiting for us
      OUTPUT.setdefault(session_id, gevent.queue.Queue())
      yield "data: \n\n"
      continue
    else:
      output.rstrip()
      yield "data: "+output+"\n\n";

@bottle.route("/log_msg_request")
def send_log():
  session_id = bottle.request.GET["session_id"]
  return json.dumps(MyLogHandler(session_id).queue.get())

@bottle.get("/completion_request")
def send_completion():
  text = bottle.request.GET["text"]
  """tmp = filter(None, re.split(r'[ ;]', text))
  if len(tmp) > 0:
    text = tmp[-1]
  else:
    text = ""
  completion_start_index = text.rfind(text)
  """
  script = jedi.Script(text, 1, len(text))
  completions = script.completions()
  if len(completions) == 1:
    cmd = completions[0].complete
  else:
    cmd = text
  import pdb;pdb.set_trace() 
  return json.dumps({ "possibilities": [x.complete for x in script.completions()], "cmd": cmd })
  """possibilities = []
  i = 0
  while True:
    possibility = INTERPRETER.completer.complete(text, i)
    if possibility is None:
      break
    else:
      if len(possibilities) > 0 and possibility == possibilities[0]:
        break
      possibilities.append(possibility)
    i += 1
    if len(possibilities) == 1:
      cmd = text[:completion_start_index]+possibilities[0]
    else:
      cmd = text
  return json.dumps({ "possibilities":possibilities, "cmd": cmd })
  """
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
    sys.__stdout__.write("storing command %r for history for client %s\n" % (python_code_to_execute, session_id))
    HISTORY.setdefault(session_id, []).append(python_code_to_execute)
    CODE_EXECUTION[session_id] = gevent.spawn(do_execute, python_code_to_execute) 
    res = CODE_EXECUTION[session_id].get()
    #while output_queue.qsize()>0:
    #  time.sleep(0.01) #let time for output to be flushed
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

def serve_forever(port=None):
  gevent.monkey.patch_all()
  bottle.run(server="gevent", host="0.0.0.0", port=port)

def set_interpreter(interpreter_object):
  global INTERPRETER
  INTERPRETER = interpreter_object


if __name__=="__main__":
    usage = "usage: \%prog [-p<port>]"
    
    parser = optparse.OptionParser(usage)
    parser.add_option('-p', '--port', dest='port', type='int',
                      help='Port to listen on (default 8099)', default=8099, action='store')
    
    options, args = parser.parse_args()

    logging.basicConfig()
    logging.getLogger().setLevel(logging.DEBUG)

    set_interpreter(InteractiveInterpreter())
    serve_forever(options.port)
    
