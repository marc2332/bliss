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

@web_app.route("/<dir>/<path:path>")
def static_file(dir, url):
  return flask.send_from_directory(os.path.join(os.path.dirname(__file__), dir), path)

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
  return flask.json.dumps(cfg.names_list)
