import flask
import flask.json
import os
import pkgutil
from .. import client
from .. import connection
from ... import static
from ... import plugins

web_app = flask.Flask(__name__)
beacon_port = None

def get_config():
  global __config
  try:
    return __config
  except NameError:
    beacon_conn = connection.Connection('localhost', beacon_port)
    client._default_connection = beacon_conn
    __config = static.get_config()
  return __config

@web_app.route("/")
def index():
  return flask.send_from_directory(os.path.dirname(__file__), "index.html")

@web_app.route("/<dir>/<path:filename>")
def static_file(dir, filename):
  return flask.send_from_directory(os.path.join(os.path.dirname(__file__), dir), filename)

@web_app.route("/db_files")
def db_files():
  cfg = get_config()

  db_files, _ = zip(*client.get_config_db_files())

  return flask.json.dumps(db_files)

@web_app.route("/objects/")
def objects():
  cfg = get_config()

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
  cfg = get_config()
  obj_cfg = cfg.get_config(name)
  if obj_cfg is None:
      return ""
  if obj_cfg.plugin != "default":
      m = __import__('beacon.plugins.%s' % obj_cfg.plugin, fromlist=[None])
      return flask.json.dumps({"html": m.get_html(obj_cfg)}) 
  else:
      return flask.json.dumps(obj_cfg)

@web_app.route("/config/reload")
def reload_config():
  cfg = get_config()
  cfg.reload()
  return ""

@web_app.route("/plugins")
def list_plugins():
  pkgpath = os.path.dirname(plugins.__file__)
  return flask.json.dumps([name for _,name,_ in pkgutil.iter_modules([pkgpath])])

