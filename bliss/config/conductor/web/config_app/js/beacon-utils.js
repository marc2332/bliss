/* -*- coding: utf-8 -*- */
/*
 * This file is part of the bliss project
 *
 * Copyright (c) 2015-2019 Beamline Control Unit, ESRF
 * Distributed under the GNU LGPLv3. See LICENSE for more info.
 */

var BEACON_TREES = {
  files: null,
  items: null,
  plugins: null,
  tags: null,
  sessions: null,
};

function get_tree_options() {
  var options = {
    collapseIcon: "fa fa-minus-square-o",
    expandIcon: "fa fa-plus-square-o",
    emptyIcon: "fa",
    nodeIcon: "fa fa-stop",
    checkedIcon: "fa fa-check-square-o",
    uncheckedIcon: "fa fa-square-o",
    searchResultBackColor: "#FFAAAA",
    searchResultColor: "#FFFFFF",
    highlightSelected: true,
    highlightSearchResults: true,
    levels: 1,
    multiSelect: false,
    showBorder: true,
    showIcon: true,
    showCheckbox: false,
    showTags: true,
  }
  return options;
}

function build_nodes(tree_data, level) {
  var result = [];
  $.each(tree_data, function(name, info) {
    var node = info[0];
    node.text = name;
    node.tags = node.tags;
    var nodes = build_nodes(info[1], level + 1);
    if (nodes.length > 0) {
      node.nodes = nodes;
    }
    result.push(node);
  });
  return result;
}

function reload_tree(tree, options) {
  var url = "tree/" + options.perspective;
  $.get(url, function(data) {
    var tree_options = get_tree_options();
    $.each(options, function(k, v) {
      tree_options[k] = v;
    });
    var data = build_nodes(data, 0);
    BEACON_TREES[options.perspective] = data;
    tree_options.data = data;
    tree.treeview(tree_options);
  }, "json");
}

function show_file(node, panel) {
  show_filename(node.path, panel);
}

function show_filename(filename, panel) {
  $.get("db_file_editor/" + filename, function(data) {
    panel.empty();
    if (data.html === undefined) {
      var form = $("<form></form>");
      form.addClass("form-group");
      panel.html(form);
      var text_area = $("<textarea></textarea>");
      text_area.addClass("form-control");
      var content = data.content;
      text_area.val(content);
      form.append(text_area);
    } else {
      panel.html(data.html);
    }
    panel.attr("style", "visibility: visible");
  }, "json");
}

function show_item(name, panel) {
  $.get("page/" + name, function(data) {
    show_html_data(data, panel);
  }, "json");
}

function show_main(panel) {
  $.get("main/", function(data) {
    show_html_data(data, panel);
  }, "json");
}

function show_html_data(data, panel) {
  if (panel === undefined) {
    panel = $("#content-panel");
  }
  if (data === null) {
    panel.empty();
    panel.attr("style", "visibility: hidden");
  } else {
    panel.html(data.html);
    panel.attr("style", "visibility: visible");
  }
}

function show_node(node, panel) {
  if (node.type == "file") {
    show_file(node, panel);
  }
  else if (node.type == "folder") {
    /* TODO */
  }
  else {
    show_item(node.name, panel);
  }
}

function configure_file_editor(tag_name, file_type) {
  var file_editor = ace.edit(tag_name);
  var session = file_editor.getSession();
  session.setMode("ace/mode/" + file_type);
  session.setNewLineMode("unix");
  session.setTabSize(4);
  session.setUseSoftTabs(true);
  file_editor.setHighlightActiveLine(true);
  file_editor.setReadOnly(false);
  file_editor.setShowPrintMargin(false);
  return file_editor;
}

function reload_config(on_success) {
  $.ajax({
    url : "config/reload",
    success: on_success,
  });
}

function save_file(file_name, content, on_success) {
  var form = new FormData();
  form.append("file_content", content);
  $.ajax({
    url: "db_file/" + file_name,
    type: "PUT",
    contentType: false,
    processData: false,
    data: form,
    success: on_success,
  });
}

function __send_form(url, form, on_success) {
  $.ajax({
    url: url,
    type: "POST",
    cache: false,
    contentType: false,
    processData: false,
    data: form,
    success: on_success,
  });
}

function add_file(filename, on_success) {
  if (filename[0] === "/") {
    filename = filename.substring(1);
  }
  console.log("add file " + filename);
  var form = new FormData();
  form.append("file", filename);
  __send_form("add_file", form, on_success);
}

function add_folder(folder, on_success) {
  if (folder[0] === "/") {
    folder = folder.substring(1);
  }
  console.log("add folder " + folder);
  var form = new FormData();
  form.append("folder", folder);
  __send_form("add_folder", form, on_success);
}

function remove_path(path, on_success) {
  console.log("remove file/directory " + path);
  var form = new FormData();
  form.append("file", path);
  __send_form("remove_file", form, on_success);
}

function move_path(src_path, dst_path, on_success) {
/*
  var src_dir = src_path.substring(0, src_path.lastIndexOf("/") + 1);
  var src_file_name = src_path.replace(/^.*[\\\/]/, '')
*/
  console.log("move file/directory from '" + src_path + "' to '" + dst_path + "'");
  if (dst_path !== null) {
    var form = new FormData();
    form.append("src_path", src_path);
    form.append("dst_path", dst_path);
    __send_form("move_path", form, on_success);
  }
}

function show_notification(msg, type, fadeOut, fadeOutDelay) {
  if (type === undefined) {
    type = "success";
  }
  if (fadeOut === undefined) {
    fadeOut = true;
  }
  if (fadeOutDelay === undefined) {
    if (type === "success") {
      fadeOutDelay = 5000;
    }
        else if (type === "info") {
          fadeOutDelay = 8000;
        }
    if (type === "warning") {
      fadeOutDelay = 12000;
        }
    if (type === "danger") {
      fadeOutDelay = 15000;
    }
  }

  $(".top-right").notify({
    message: { html: msg },
    closable: true,
    transition: "fade",
    fadeOut: {
      enabled: fadeOut,
      delay: fadeOutDelay,
    },
    type: type,
  }).show();
}
