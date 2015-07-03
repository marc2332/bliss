import os
import sys
import pkgutil

import flask
import flask.json

from jinja2 import Environment, FileSystemLoader

from .. import client
from .. import connection
from ... import static
from ... import plugins

web_app = flask.Flask(__name__)
beacon_port = None

__this_file = os.path.realpath(__file__)
__this_path = os.path.dirname(__this_file)

def get_config():
  global __config
  try:
    return __config
  except NameError:
    beacon_conn = connection.Connection('localhost', beacon_port)
    client._default_connection = beacon_conn
    __config = static.get_config()
  return __config

def get_jinja2():
    global __environment
    try:
      return __environment
    except NameError:
      __environment = Environment(loader=FileSystemLoader(__this_path))
    return __environment

@web_app.route("/")
def index():
  return flask.send_from_directory(__this_path, "index.html")

@web_app.route("/<dir>/<path:filename>")
def static_file(dir, filename):
  return flask.send_from_directory(os.path.join(__this_path, dir), filename)

@web_app.route("/db_files")
def db_files():
  cfg = get_config()

  db_files, _ = zip(*client.get_config_db_files())

  return flask.json.dumps(db_files)

@web_app.route("/db_file/<path:filename>")
def get_db_file(filename):
  if flask.request.data:
    print flask.request.data
    client.set_config_db_file(filename, flask.request.data)
    return "ok"
  else:
    cfg = get_config()
    db_files = dict(client.get_config_db_files())
    return flask.json.dumps(dict(name=filename, content=db_files[filename]))

@web_app.route("/db_file_editor/<path:filename>")
def get_db_file_editor(filename):
  cfg = get_config()

  db_files = dict(client.get_config_db_files())

  template = get_jinja2().select_template(("editor.html",))
  html = template.render(dict(name=filename, content=db_files[filename]))
  return flask.json.dumps(dict(html=html, name=filename))

@web_app.route("/objects/")
def objects():
  cfg = get_config()

  db_files, _ = map(list, zip(*client.get_config_db_files()))

  for name in cfg.names_list:
    config = cfg.get_config(name)
    db_files.append(os.path.join(config.filename, name))

  result = dict()
  for db_file in db_files:
    current_level = result
    for part in db_file.split(os.path.sep):
      current_level.setdefault(part, [db_file, dict()])
      current_level = current_level[part][1]
  return flask.json.dumps(result)

@web_app.route("/objects/<name>")
def get_object_config(name):
  cfg = get_config()
  obj_cfg = cfg.get_config(name)
  if obj_cfg is None:
      return ""
  if obj_cfg.plugin not in ("default", None):
    try:
      mod_name = 'bliss.config.plugins.%s' % obj_cfg.plugin
      m = __import__(mod_name, fromlist=[None])
      if hasattr(m, "get_html"):
        obj_cfg = {"html": m.get_html(obj_cfg), "name": name}
    except ImportError:
      # plugin has an error
      sys.excepthook(*sys.exc_info())
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
