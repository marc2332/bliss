/* -*- coding: utf-8 -*- */
/*
 * This file is part of the bliss project
 *
 * Copyright (c) 2016 Beamline Control Unit, ESRF
 * Distributed under the GNU LGPLv3. See LICENSE for more info.
 */

function getTreeExample() {
  var data = [
    {
      text: "OH1",
      icon: "fa fa-folder-open",
      nodes: [
        { text: "gasblower.yml",
          icon: "fa fa-file-text", },
        { text: "wago1.yml" },
      ]
    },
    {
      text: "OH2",
      nodes: [
        { text: "ll.yml" },
        { text: "wago2.yml" },
        { text: "iceid315.yml",
          nodes: [
            { text: "gmy" },
            { text: "eslb" },
            { text: "esrb" },
            { text: "estb" },
            { text: "esbb" },
          ]
        },
      ]
    },
    {
      text: "EH",
      nodes: [
        { text: "hemd.yml" },
        { text: "wago3.yml" },
        { text: "iceid315.yml",
          nodes: [
            { text: "th" },
            { text: "tth" },
            { text: "chi" },
            { text: "phi" },
          ]
        },
      ]
    },
  ];
  return data;
}

function __get_tree_options() {
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
    levels: 2,
    multiSelect: false,
    showBorder: false,
    showIcon: true,
    showCheckbox: false,
  }
  return options;
}

function build_nodes(tree_data, level) {
  var result = [];
  $.each(tree_data, function(name, info) {
    var node = info[0];
    var nodes = build_nodes(info[1], level + 1);
    node.text = name;
    if (nodes.length > 0) {
      node.nodes = nodes;
    }
    result.push(node);
  });
  return result;
}

function reload_tree(tree, options) {
  $.get(options.url, function(data) {
    var tree_options = __get_tree_options();
    $.each(options, function(k, v) {
      tree_options[k] = v;
    });
    tree_options.data = build_nodes(data, 0);
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

function show_item(node, panel) {
  $.get("items/" + node.name, function(data) {
    show_html_data(data, panel);
  }, "json");
}

function show_main(panel) {
  $.get("main/", function(data) {
    show_html_data(data, panel);
  }, "json");
}

function show_html_data(data, panel) {
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
    show_item(node, panel);
  }
}

function configure_file_editor(tag_name, file_name, file_type) {
  var file_editor = ace.edit(tag_name);
  var session = file_editor.getSession();
  session.setMode("ace/mode/" + file_type);
  session.setNewLineMode("unix");
  session.setTabSize(4);
  session.setUseSoftTabs(true);
  file_editor.setHighlightActiveLine(true);
  file_editor.setReadOnly(false);
  file_editor.setShowPrintMargin(false);
  file_editor.getSession().on("change", function(e) {
    $("#save_editor_changes").button().removeClass("disabled");
    $("#revert_editor_changes").button().removeClass("disabled");
  });
  $("#save_editor_changes").on("click", function() {
    var form = new FormData();
    form.append("file_content", file_editor.getValue());
    $.ajax({
      url: "db_file/" + file_name,
      type: "PUT",
      contentType: false,
      processData: false,
      data: form,
      success: function() {
	request = $.ajax({
	  url : "config/reload",
	  success: function() {
	    reload_trees();
	    show_notification(file_name +" saved!", "success");
	  }});
      }
    });
  });
  $("#revert_editor_changes").on("click", function() {
    $.get("db_file/" + file_name, function(data) {
      file_editor.setValue(data.content);
    }, "json");
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
