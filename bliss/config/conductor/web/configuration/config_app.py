# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import sys
import pkgutil
import functools

import gevent.lock

import flask
import flask.json

from jinja2 import Environment, FileSystemLoader

from bliss.config.conductor import server
from bliss.config.conductor import client
from bliss.config.conductor import connection
from bliss.config import static
from bliss.config import plugins
from bliss.common import event


web_app = flask.Flask(__name__)
beacon_port = None

__this_file = os.path.realpath(__file__)
__this_path = os.path.dirname(__this_file)


def check_config(f):
    functools.wraps(f)

    def wrapper(self, *args, **kwargs):
        self.get_config()
        return f(self, *args, **kwargs)

    return wrapper


class WebConfig(object):

    EXT_MAP = {
        "": dict(type="text", icon="file-o"),
        "txt": dict(type="text", icon="file-o"),
        "md": dict(type="markdown", icon="file-o"),
        "yml": dict(type="yaml", icon="file-text-o"),
        "py": dict(type="python", icon="file-code-o"),
        "html": dict(type="html", icon="file-code-o"),
        "css": dict(type="css", icon="file-code-o"),
        "js": dict(type="javascript", icon="file-code-o"),
        "png": dict(type="image", icon="file-image-o"),
        "jpg": dict(type="image", icon="file-image-o"),
        "jpeg": dict(type="image", icon="file-image-o"),
        "gif": dict(type="image", icon="file-image-o"),
        "tif": dict(type="image", icon="file-image-o"),
        "tiff": dict(type="image", icon="file-image-o"),
    }

    def __init__(self):
        self.__new_config = False
        self.__lock = gevent.lock.RLock()
        self.__items = None
        self.__tree_items = None
        self.__tree_files = None
        self.__tree_plugins = None
        self.__tree_tags = None
        self.__tree_sessions = None
        beacon_conn = connection.Connection("localhost", beacon_port)
        client._default_connection = beacon_conn
        event.connect(server.__name__, "config_changed", self.__on_config_changed)

    def __on_config_changed(self):
        with self.__lock:
            self.__new_config = True
            self.__items = None
            self.__tree_items = None
            self.__tree_files = None
            self.__tree_plugins = None
            self.__tree_tags = None
            self.__tree_sessions = None

    def get_config(self):
        with self.__lock:
            cfg = static.get_config()
            if self.__new_config:
                cfg.reload()
                self.__new_config = False
            return cfg

    @property
    def items(self):
        if self.__items is None:
            self.__items = self.__build_items()
        return self.__items

    @property
    def tree_items(self):
        if self.__tree_items is None:
            self.__tree_items = self.__build_tree_items()
        return self.__tree_items

    @property
    def tree_files(self):
        if self.__tree_files is None:
            self.__tree_files = self.__build_tree_files()
        return self.__tree_files

    @property
    def tree_plugins(self):
        if self.__tree_plugins is None:
            self.__tree_plugins = self.__build_tree_plugins()
        return self.__tree_plugins

    @property
    def tree_tags(self):
        if self.__tree_tags is None:
            self.__tree_tags = self.__build_tree_tags()
        return self.__tree_tags

    @property
    def tree_sessions(self):
        if self.__tree_sessions is None:
            self.__tree_sessions = self.__build_tree_sessions()
        return self.__tree_sessions

    def __build_items(self):
        cfg = self.get_config()
        items = {}
        for name in cfg.names_list:
            config = cfg.get_config(name)
            get_tree = _get_config_plugin(config, "get_tree")
            item = None
            if get_tree:
                try:
                    item = get_tree(config, "items")
                except:
                    pass
            if item is None:
                item = dict(type="item", path=name, icon="fa fa-question")
            item["name"] = name
            item["tags"] = _get_config_user_tags(config)
            item["plugin"] = config.get("plugin")
            items[name] = item
        return items

    def __build_tree_sessions(self):
        cfg = self.get_config()
        sessions = {}
        for name, item in self.items.items():
            config = cfg.get_config(name)
            if config.plugin != "session":
                continue
            session_items = {}
            #            for iname, item in self.items.items():

            sessions[name] = item, session_items
        return sessions

    def __build_tree_items(self):
        items = self.items
        result = {}
        for name, item in items.items():
            current_level = result
            db_file = item["path"]
            parts = db_file.split(os.path.sep)
            full_part = ""
            for part in parts[:-1]:
                full_part = os.path.join(full_part, part)
                p_item = items.get(full_part)
                if p_item is None:
                    p_item = dict(type="folder", path=full_part, icon="fa fa-folder")
                current_level.setdefault(part, [p_item, dict()])
                current_level = current_level[part][1]
            current_level.setdefault(parts[-1], [item, dict()])
        return result

    def __build_tree_plugins(self):
        cfg = self.get_config()
        result = {}
        for name, item in self.items.items():
            config = cfg.get_config(name)
            plugin_name = config.plugin or "__no_plugin__"
            plugin_data = result.get(plugin_name)
            if plugin_data is None:
                plugin_data = [
                    dict(type="folder", path=plugin_name, icon="fa fa-folder"),
                    {},
                ]
                result[plugin_name] = plugin_data
            plugin_items = plugin_data[1]
            plugin_items[name] = [item, {}]
        return result

    def __build_tree_tags(self):
        cfg = self.get_config()
        result = {}
        for name, item in self.items.items():
            config = cfg.get_config(name)
            for tag in item["tags"] or ["__no_tag__"]:
                tag_data = result.get(tag)
                if tag_data is None:
                    tag_data = [dict(type="folder", path=tag, icon="fa fa-folder"), {}]
                    result[tag] = tag_data
                tag_items = tag_data[1]
                tag_items[name] = [item, {}]
        return result

    def __build_tree_files(self):
        cfg = self.get_config()

        src, dst = client.get_config_db_tree(), {}
        self.__build_tree_files__(src, dst)

        items = {}
        for name in cfg.names_list:
            config = cfg.get_config(name)
            get_tree = _get_config_plugin(config, "get_tree")
            item = None
            if get_tree:
                try:
                    item = get_tree(config, "files")
                except:
                    pass
            if item is None:
                item = dict(
                    type="item",
                    path=os.path.join(config.filename, name),
                    icon="fa fa-question",
                )

            item["name"] = name
            item["tags"] = _get_config_user_tags(config)
            items[item["path"]] = name, item

        for path in sorted(items):
            name, item = items[path]
            path = item["path"]
            parent = dst
            # search file node where item is defined
            for pitem in path.split(os.path.sep):
                try:
                    parent = parent[pitem][1]
                except KeyError:
                    break
            parent[name] = [item, {}]
        return dst

    def __build_tree_files__(self, src, dst, path=""):
        for name, data in src.items():
            if name.startswith(".") or name.endswith("~") or name.endswith(".rdb"):
                continue
            item_path = os.path.join(path, name)
            sub_items = {}
            if data is None:  # a file
                ext_info = self.get_file_info(name)
                meta = dict(
                    type="file", path=item_path, icon="fa fa-" + ext_info["icon"]
                )
            else:
                meta = dict(type="folder", path=item_path, icon="fa fa-folder")
                self.__build_tree_files__(data, sub_items, path=item_path)
            dst[name] = [meta, sub_items]
        return dst

    @check_config
    def get_file_info(self, file_name):
        ext = file_name.rpartition(os.path.extsep)[2]
        if "." not in file_name:
            ext = ""
        return self.EXT_MAP.setdefault(ext, dict(type=ext, icon="question"))


__config = WebConfig()


def __get_jinja2():
    global __environment
    try:
        return __environment
    except NameError:
        __environment = Environment(loader=FileSystemLoader(__this_path))
    return __environment


def _get_config_plugin(cfg, member=None):
    if cfg is None:
        return
    if cfg.plugin in ("default", None):
        return
    return __get_plugin(cfg.plugin, member=member)


def __get_plugin(name, member=None):
    try:
        mod_name = "bliss.config.plugins.%s" % name
        mod = __import__(mod_name, fromlist=[None])
    except ImportError:
        # plugin has an error
        mod = None
        return
    if member:
        try:
            return getattr(mod, member)
        except:
            # plugin has no member
            return
    return mod


def __get_plugin_importer():
    plugins_path = os.path.dirname(plugins.__file__)
    return pkgutil.ImpImporter(path=plugins_path)


def __get_plugin_names():
    return [name for name, _ in __get_plugin_importer().iter_modules()]


def __get_plugins():
    result = {}
    for name in __get_plugin_names():
        plugin = __get_plugin(name)
        if plugin:
            result[name] = plugin
    return result


def _get_config_user_tags(config_item):
    user_tag = config_item.get(static.Config.USER_TAG_KEY, [])
    if not isinstance(user_tag, (tuple, list)):
        user_tag = [user_tag]
    return user_tag


@web_app.route("/")
def index():
    cfg = __config.get_config()
    node = cfg.root

    template = __get_jinja2().select_template(("index.html",))

    full_name = institute = node.get("institute", node.get("synchrotron"))
    laboratory = node.get("laboratory", node.get("beamline"))
    if laboratory:
        if full_name:
            full_name += " - "
        full_name += laboratory
    icon = node.get("icon", "res/logo.png")
    return template.render(
        dict(
            name=full_name,
            institute=institute,
            laboratory=laboratory,
            icon=icon,
            config=cfg,
        )
    )


@web_app.route("/<dir>/<path:filename>")
def static_file(dir, filename):
    return flask.send_from_directory(os.path.join(__this_path, dir), filename)


@web_app.route("/main/")
def main():
    cfg = __config.get_config()
    get_main = __get_plugin(cfg.root.plugin or "beamline", "get_main")
    if get_main:
        return get_main(cfg)
    else:
        return flask.json.dumps(dict(html="<h1>ups!</h1>"))


@web_app.route("/db_files")
def db_files():
    cfg = __config.get_config()
    db_files, _ = zip(*client.get_config_db_files())
    return flask.json.dumps(db_files)


@web_app.route("/db_tree")
def db_tree():
    cfg = __config.get_config
    db_tree = client.get_config_db_tree()
    return flask.json.dumps(db_tree)


@web_app.route("/db_file/<path:filename>", methods=["PUT", "GET"])
def get_db_file(filename):
    if flask.request.method == "PUT":
        # browsers encode newlines as '\r\n' so we have to undo that crap
        content = flask.request.form["file_content"].replace("\r\n", "\n")
        client.set_config_db_file(filename, content)
        event.send(server.__name__, "config_changed")
        return flask.json.dumps(dict(message="%s successfully saved", type="success"))
    else:
        cfg = __config.get_config()
        content = client.get_config_file(filename).decode("utf-8")
        return flask.json.dumps(dict(name=filename, content=content))


@web_app.route("/db_file_editor/<path:filename>")
def get_db_file_editor(filename):
    cfg = __config.get_config()

    content = client.get_config_file(filename).decode()

    file_info = __config.get_file_info(filename)
    template = __get_jinja2().select_template(("editor.html",))
    html = template.render(
        dict(name=filename, ftype=file_info["type"], content=content)
    )
    return flask.json.dumps(dict(html=html, name=filename))


@web_app.route("/items/")
def items():
    cfg = __config.get_config()

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


def get_item(cfg):
    name = cfg.get("name")
    item = dict(name=name, tags=_get_config_user_tags(cfg))
    plugin = _get_config_plugin(cfg, "get_item")
    if plugin:
        item.update(plugin(cfg))
    return item


@web_app.route("/item/<name>")
def item(name):
    cfg = __config.get_config()
    obj_cfg = cfg.get_config(name)
    return flask.json.dumps(get_item(obj_cfg))


@web_app.route("/tree/<view>")
def tree(view):
    if view == "files":
        result = __config.tree_files
    elif view == "items":
        result = __config.tree_items
    elif view == "plugins":
        result = __config.tree_plugins
    elif view == "tags":
        result = __config.tree_tags
    elif view == "sessions":
        result = __config.tree_sessions
    else:
        result = dict(message="unknown view", type="error")
    return flask.json.dumps(result)


@web_app.route("/tree/<view>/<item>")
def sub_tree(view, item):
    if view == "files":
        result = __config.tree_files
    elif view == "items":
        result = __config.tree_items
    elif view == "plugins":
        result = __config.tree_plugins
    elif view == "tags":
        result = __config.tree_tags
    elif view == "sessions":
        result = __config.tree_sessions
    else:
        return flask.json.dumps(dict(message="unknown view", type="error"))


@web_app.route("/page/<name>")
def get_item_config(name):
    cfg = __config.get_config()
    obj_cfg = cfg.get_config(name)
    plugin = _get_config_plugin(obj_cfg, "get_html")
    if plugin:
        obj_cfg = plugin(obj_cfg)
    else:
        obj_cfg = "<!-- TODO -->"
    return flask.json.dumps(dict(html=obj_cfg, name=name))


@web_app.route("/config/reload")
def reload_config():
    cfg = __config.get_config()
    cfg.reload()
    event.send(server.__name__, "config_changed")
    return flask.json.dumps(
        dict(message="Configuration fully reloaded!", type="success")
    )


@web_app.route("/plugins")
def list_plugins():
    return flask.json.dumps(__get_plugin_names())


@web_app.route("/plugin/<name>/<action>", methods=["GET", "POST", "PUT"])
def handle_plugin_action(name, action):
    plugin = __get_plugin(name, member=action)
    if not plugin:
        return ""
    return plugin(__config.get_config(), flask.request)


@web_app.route("/add_folder", methods=["POST"])
def add_folder():
    cfg = __config.get_config()
    folder = flask.request.form["folder"]

    filename = os.path.join(folder, "__init__.yml")
    node = static.Node(cfg, filename=filename)
    node.save()
    return flask.json.dumps(dict(message="Folder created!", type="success"))


@web_app.route("/add_file", methods=["POST"])
def add_file():
    cfg = __config.get_config()
    filename = flask.request.form["file"]
    node = static.Node(cfg, filename=filename)
    node.save()
    return flask.json.dumps(dict(message="File created!", type="success"))


@web_app.route("/remove_file", methods=["POST"])
def remove_file():
    cfg = __config.get_config()
    filename = flask.request.form["file"]
    client.remove_config_file(filename)
    return flask.json.dumps(dict(message="File deleted!", type="success"))


@web_app.route("/copy_file", methods=["POST"])
def copy_file():
    cfg = __config.get_config()
    src_path = flask.request.form["src_path"]
    dst_path = flask.request.form["dst_path"]

    # if destination is a directory (ends in '/'), append the
    # filename coming from source
    if dst_path.endswith(os.path.pathsep):
        dst_path = os.path.join(dst_path, os.path.split(src_path)[1])

    node = static.Node(cfg, filename=dst_path)
    node.save()

    db_files = dict(client.get_config_db_files())

    template = __get_jinja2().select_template(("editor.html",))
    html = template.render(dict(name=dst_path, content=db_files[src_path]))
    result = dict(
        name=dst_path,
        html=html,
        type="warning",
        message="File copied from <i>{0}</i> to <i>{1}</i>. <br/>"
        "You <b>must</b> edit content and change element "
        "names to clear name conflicts<br/>"
        "Don't forget to <b>save</b> in order for the changes "
        "to take effect!".format(src_path, dst_path),
    )
    return flask.json.dumps(result)


@web_app.route("/move_path", methods=["POST"])
def move_path():
    cfg = __config.get_config()
    src_path = flask.request.form["src_path"]
    dst_path = flask.request.form["dst_path"]
    client.move_config_path(src_path, dst_path)
    msg = "Moved from <i>{0}</i> to <i>{1}</i>".format(src_path, dst_path)
    return flask.json.dumps(dict(message=msg, type="success"))
