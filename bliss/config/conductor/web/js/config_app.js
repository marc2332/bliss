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

function __add_file(path) {
    if (path.indexOf(".yml", path.length - 4) === -1) {
	alert("File must end with '.yml'");
	return;
    }
    if (path[0] === "/") {
	path = path.substring(1);
    }
    console.log("add file" + path);
    var form = new FormData();
    form.append("file", path);
    __send_form("add_file", form, function(result) {
        data = $.parseJSON(result);
	tree_reload("#tree_tabs", path);
        show_yaml(path);
        notification(data.message, data.type);
    });
}

function __add_folder(path) {
    if (path[0] === "/") {
	path = path.substring(1);
    }
    console.log("add folder " + path);
    var form = new FormData();
    form.append("folder", path);
    __send_form("add_folder", form, function(result) {
        data = $.parseJSON(result);
	tree_reload("#tree_tabs", path);
        show_item(path);
        notification(data.message, data.type);
    });
}

function __remove(path) {
    console.log("remove file/directory " + path);
    var form = new FormData();
    form.append("file", path);
    __send_form("remove_file", form, function(result) {
        data = $.parseJSON(result);
	$("#edit_panel").empty();
	tree_reload("#tree_tabs");
        notification(data.message, data.type);
    });
}

function __remove_file(path) {
    var r = confirm("Are you sure you want to delete " + path + "?");
    if (r !== true) {
	return;
    }
    __remove(path);
}

function __remove_folder(path) {
    var r = confirm("Are you sure you want to folder " + path + " (all items underneath will also be deleted!) ?");
    if (r !== true) {
	return;
    }
    __remove(path);
}

function __move_path(src_path, dst_path) {
    console.log("move file/directory from '" + src_path + "' to '" + dst_path + "'");
    var form = new FormData();
    form.append("src_path", src_path);
    form.append("dst_path", dst_path);
    __send_form("move_path", form, function(result) {
        data = $.parseJSON(result);
	$("#edit_panel").empty();
	tree_reload("#tree_tabs", dst_path);
        notification(data.message, data.type);
    });
}

function __copy_file(src_path, dst_path) {
    console.log("copy file '" + src_path + "' to '" + dst_path + "'");
    var form = new FormData();
    form.append("src_path", src_path);
    form.append("dst_path", dst_path);
    __send_form("copy_file", form, function(result) {
        data = $.parseJSON(result);
	tree_reload("#tree_tabs", dst_path);
        show_html_data(data);
        notification(data.message, data.type);
    });
}

function add_file(dft) {
    var path = prompt("YAML file name (full path including '.yml' extension)?", dft);
    if (path !== null) {
	__add_file(path);
    }
}

function add_folder(dft) {
    var path = prompt("Directory name (full path)?", dft);
    if (path !== null) {
	__add_folder(path);
    }
}

function tree_add_folder(obj) {
    var path = prompt("Directory name?");
    if (path !== null) {
	path =  this.data.path + "/" + path;
	__add_folder(path);
    }
}

function tree_add_file(obj) {
    var path = prompt("File name (must have suffix '.yml')?");
    if (path !== null) {
	path = this.data.path + "/" + path;
	__add_file(path);
    }
}

function tree_copy_file(obj) {
    var path = prompt("Destination (ex: OH/motion/ice2.yml)?");
    if (path !== null) {
	__copy_file(this.data.path, path);
    }
}

function tree_rename_file(obj) {
    var src_dir_name = this.data.path.substring(0, this.data.path.lastIndexOf("/")+1);
    var src_file_name = this.data.path.replace(/^.*[\\\/]/, '')
    var dst_file_name = prompt("New file name?", src_file_name);
    if (dst_file_name !== null) {
        __move_path(this.data.path, src_dir_name + dst_file_name);
    }
}

function tree_rename_folder(obj) {
    var src_dir_name = this.data.path.substring(0, this.data.path.lastIndexOf("/")+1);
    var src_folder_name = this.data.path.replace(/^.*[\\\/]/, '')
    var dst_folder_name = prompt("New folder name?", src_folder_name);
    if (dst_folder_name !== null) {
        __move_path(this.data.path, src_dir_name + dst_folder_name);
    }
}

function tree_move_path(obj) {
    var path = prompt("new path (ex: OH/motion)?");
    if (path !== null) {
	__move_path(this.data.path, path);
    }
}

function tree_remove_file(obj) {
    __remove_file(this.data.path);
}

function tree_remove_folder(obj) {
    __remove_folder(this.data.path);
}

function tree_context_menu(node) {
    var items = {}
    if (node.data.type == 'file') {
	items.add_item = {
	    label: "Add item",
	    icon: "fa fa-star",
	    separator_before: false,
	    _disabled: true,
	    action: function(n) { console.log("add item"); },
	};
	items.copy_item = {
            label: "Copy",
            icon: "fa fa-copy",
	    separator_before: true,
	    _disabled: false,
	    action: tree_copy_file.bind(node),
	};
	items.rename_item = {
            label: "Rename",
            icon: "fa fa-edit",
	    separator_before: false,
	    _disabled: false,
	    shortcut: 113,
	    shortcut_label: "F2",
	    action: tree_rename_file.bind(node),
	};
	items.move_item = {
            label: "Move",
            icon: "fa fa-reorder",
	    separator_before: false,
	    _disabled: false,
	    action: tree_move_path.bind(node),
	};
	items.delete_item = {
	    label: "Delete",
	    icon: "fa fa-remove",
	    separator_before: false,
	    _disabled: false,
	    action: tree_remove_file.bind(node),
	};
    }
    else if (node.data.type == 'folder') {
	items.add_file = {
	    label: "Add YAML file",
	    icon: "fa fa-file",
	    _disabled: false,
	    action: tree_add_file.bind(node),
	};
	items.add_folder = {
	    label: "Add folder",
	    icon: "fa fa-folder",
	    _disabled: false,
	    action: tree_add_folder.bind(node),
	};
	items.rename_item = {
            label: "Rename",
            icon: "fa fa-edit",
	    separator_before: true,
	    _disabled: false,
	    shortcut: 113,
	    shortcut_label: "F2",
	    action: tree_rename_folder.bind(node),
	};
	items.move_item = {
            label: "Move",
            icon: "fa fa-reorder",
	    separator_before: false,
	    _disabled: false,
	    action: tree_move_path.bind(node),
	};
	items.delete_item = {
	    label: "Delete",
	    icon: "fa fa-remove",
	    separator_before: false,
	    _disabled: false,
	    action: tree_remove_folder.bind(node),
	};
    }

    return items;
}

function tree_reload(tree_name, selected_item_name) {
    var fill_node = function(data, parent_node, level) {
        var opened = false;
        if (level<1) {
            opened = true;
        }
        $.each(data, function(key, value) {
	    node_info = value[0];
	    selected = selected_item_name === node_info.path;
            var new_node = {
		text: key,
		children: [],
		icon: node_info.icon,
		data: {
		    type: node_info.type,
		    path: node_info.path,
		    icon: node_info.icon,
		},
		state: {
                    opened: opened,
		    selected: selected,
		}
            };
            parent_node.push(new_node);
            fill_node(value[1], new_node.children, level + 1);
        });
    };

    $.get("tree/objects", function(data) {
        var _tree = $(tree_name);
	var tree = $(".beacon-tree.objects-perspective", _tree);
        tree.jstree("destroy");

        var tree_struct = {
            core: {
		data: [],
		animation: 0,
		multiple: false
            },
            plugins: ["contextmenu", "search", "dnd"],
	    contextmenu: {
	      items: tree_context_menu.bind(this)
            },
            search: {
		case_insensitive: true,
		show_only_matches: true,
	    },
        };

        fill_node(data, tree_struct.core.data, 0);

        tree.jstree(tree_struct);
	tree.bind("select_node.jstree", on_node_selected);
    }, "json");

    $.get("tree/files", function(data) {
        var _tree = $(tree_name);
	var tree = $(".beacon-tree.files-perspective", _tree);
        tree.jstree("destroy");

        var tree_struct = {
            core: {
		data: [],
		animation: 0,
		multiple: false
            },
            plugins: ["contextmenu", "search", "dnd"],
	    contextmenu: {
	      items: tree_context_menu.bind(this)
            },
            search: {
		case_insensitive: true,
		show_only_matches: true,
	    },
        };

        fill_node(data, tree_struct.core.data, 0);

        tree.jstree(tree_struct);
	tree.bind("select_node.jstree", on_node_selected);
    }, "json");
}

function on_node_selected(ev, data) {
    var node_type = data.node.data.type;
    if (node_type === "file") {
        on_yaml_node_selected(ev, data);
    } else {
        on_item_node_selected(ev, data);
    }
}

function on_yaml_node_selected(ev, data) {
    var file_path = data.node.data.path;
    show_yaml(file_path);
}

function show_yaml(file_path) {
   $.get("db_file_editor/" + file_path, function(data) {
        $("#right_panel").empty();
        if (data.html === undefined) {
            var form = $("<form></form>");
            form.addClass("form-group");
            $("#right_panel").html(form);
            var text_area = $("<textarea></textarea>");
            text_area.addClass("yaml");
            text_area.addClass("form-control");
            var content = data.content;
            text_area.val(content);
            form.append(text_area);
        } else {
            $("#right_panel").html(data.html);
        }
        $("#right_panel").attr("style", "visibility: visible");
    }, "json");
}

function on_item_node_selected(ev, data) {
    var node_name = data.node.text;
    show_item(node_name);
}

function show_item(item_name) {
    $.get("objects/" + item_name, show_html_data, "json");
}

function show_main() {
    $.get("main/", show_html_data, "json");
}

function show_html_data(data) {
    if (data === null) {
        $("#right_panel").empty();
        $("#right_panel").attr("style", "visibility: hidden");
    } else {
        $("#right_panel").html(data.html);
        $("#right_panel").attr("style", "visibility: visible");
    }
}

function configure_yaml_editor(tag_name, file_name) {
    var yaml_editor = ace.edit(tag_name);
    var session = yaml_editor.getSession();
    session.setMode("ace/mode/yaml");
    session.setTabSize(4);
    yaml_editor.setHighlightActiveLine(true);
    yaml_editor.setReadOnly(false);
    yaml_editor.setShowPrintMargin(false);
    yaml_editor.getSession().on("change", function(e) {
        $("#save_editor_changes").button().removeClass("disabled");
        $("#revert_editor_changes").button().removeClass("disabled");
    });
    $("#save_editor_changes").on("click", function() {
        var form = new FormData();
        form.append("yml_file", yaml_editor.getValue());
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
			tree_reload("#tree_tabs", file_name);
			notification(file_name +" saved!", "success");
		    }});
            }
        });
    });
    $("#revert_editor_changes").on("click", function() {
        $.get("db_file/" + file_name, function(data) {
            yaml_editor.setValue(data.content);
        }, "json");
    });
}

function on_plugin_action(plugin, action) {
    console.log("plugin '" + plugin + "' action: " + action);
    $.ajax({
	url: action,
	type: "GET",
	cache: false,
	contentType: false,
	processData: false,
	data: null,
	success: function(action_result) {
            data = $.parseJSON(action_result);
//	    tree_reload("#tree_tabs");
            show_html_data(data);
            notification(data.message, data.type);
	}
    });
}

function notification(msg, type, fadeOut, fadeOutDelay) {
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