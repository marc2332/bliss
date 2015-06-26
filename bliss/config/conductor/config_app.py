import flask
import flask.json
import os
from . import client
from . import connection
from .. import static

web_app = flask.Flask(__name__)
beacon_port = None
beacon_conn = None
cfg = None

def init():
  global beacon_conn
  global cfg
  beacon_conn = connection.Connection('localhost', beacon_port)
  client._default_connection = beacon_conn
  cfg = static.get_config()

@web_app.route("/")
def index():
  return flask.send_from_directory(os.path.dirname(__file__), "index.html")

@web_app.route("/<dir>/<path:filename>")
def static_file(dir, filename): 
  return flask.send_from_directory(os.path.join(os.path.dirname(__file__), dir), filename)

@web_app.route("/db_files")
def db_files():
  if cfg is None:
    init()
  db_files, _ = zip(*client.get_config_db_files())

  return flask.json.dumps(db_files) 

@web_app.route("/objects/")
def objects():
  if cfg is None:
    init()

  db_files, _ = map(list, zip(*client.get_config_db_files()))

  #result = list()
  for name in cfg.names_list:
    config = cfg.get_config(name)
    db_files.append(os.path.join(config.filename, name))
    #result.append({ "name": name, "filename": config.filename, "plugin": config.plugin })

  result = dict()
  for path in [x.split(os.path.sep) for x in db_files]:
    current_level = result
    for part in path:
      current_level.setdefault(part, dict())
      current_level = current_level[part]
  
  return flask.json.dumps(result)

@web_app.route("/objects/<name>")
def get_object_config(name):
  if cfg is None:
    init()

  result = cfg.get_config(name)

  return flask.json.dumps(result)

