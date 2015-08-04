function __add_file(path) {
    if (path.indexOf(".yml", path.length - 4) === -1) {
	alert("File must end with '.yml'");
	return;
    }
    if (path[0] === "/") {
	path = path.substring(1);
    }
    console.log("add file " + path);
    var formData = new FormData();
    formData.append("file", path);

    $.ajax({
	url: "add_file",
	type: "POST",
	cache: false,
	contentType: false,
	processData: false,
	data: formData,
	success: function(result) {
            data = $.parseJSON(result);
	    tree_reload("#fs_tree", path);
            show_yaml(path);
            write_message(data.message, data.type);
	}
    });
}

function __add_folder(path) {
    if (path[0] === "/") {
	path = path.substring(1);
    }
    console.log("add folder " + path);
    var formData = new FormData();
    formData.append("folder", path);

    $.ajax({
	url: "add_folder",
	type: "POST",
	cache: false,
	contentType: false,
	processData: false,
	data: formData,
	success: function(result) {
            data = $.parseJSON(result);
	    tree_reload("#fs_tree", path);
            show_item(path);
            write_message(data.message, data.type);
	}
    });
}

function add_file() {
    var path = prompt("YAML file name (full path including '.yml extension)?");
    if (path !== null) {
	__add_file(path);
    }
}

function __remove(path) {
    console.log("remove file/directory " + path);
    var formData = new FormData();
    formData.append("file", path);

    $.ajax({
	url: "remove_file",
	type: "POST",
	cache: false,
	contentType: false,
	processData: false,
	data: formData,
	success: function(result) {
            data = $.parseJSON(result);
	    tree_reload("#fs_tree");
	    $("#edit_form").empty();
            write_message(data.message, data.type);
	}
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

function add_folder() {
    var path = prompt("Directory name (full path)?");
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
    var path = prompt("File name (must have suffix '.yml'?");
    if (path !== null) {
	path = this.data.path + "/" + path;
	__add_file(path);
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
	    _disabled: true,
	    action: function(n) { console.log("add item"); },
	};
	items.rename_item = {
            label: "Rename",
            icon: "fa fa-edit",
	    separator_before: true,
	    _disabled: true,
	    shortcut: 113,
	    shortcut_label: "F2",
	    action: function() { console.log("rename item"); },
	};

	items.delete_item = {
	    label: "Delete",
	    icon: "fa fa-remove",
	    separator_before: true,
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
	    _disabled: true,
	    action: tree_add_folder.bind(node),
	};
	items.rename_item = {
            label: "Rename",
            icon: "fa fa-edit",
	    separator_before: true,
	    _disabled: true,
	    shortcut: 113,
	    shortcut_label: "F2",
	    action: function() { console.log("rename item"); },
	};

	items.delete_item = {
	    label: "Delete",
	    icon: "fa fa-remove",
	    separator_before: true,
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

    $.get("tree/files", function(data) {
        var tree = $(tree_name);
        tree.jstree("destroy");
	//var js_tree = tree.jstree();

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
        $("#edit_form").empty();
        if (data.html === undefined) {
            var form = $("<form></form>");
            form.addClass("form-group");
            $("#edit_form").html(form);
            var text_area = $("<textarea></textarea>");
            text_area.addClass("yaml");
            text_area.addClass("form-control");
            var content = data.content;
            text_area.val(content);
            form.append(text_area);
        } else {
            $("#edit_form").html(data.html);
        }
        $("#edit_panel").attr("style", "visibility: visible");
    }, "json");
}

function on_item_node_selected(ev, data) {
    var node_name = data.node.text;
    show_item(node_name);
}

function show_item(item_name) {
    console.log("showing item " + item_name);
    $.get("objects/" + item_name, function(data) {
        $("#edit_form").empty();
        if (data === null) {
            $("#edit_panel").attr("style", "visibility: hidden");
        } else {
            if (data.html === undefined) {
                var form = $("<form></form>");
                form.addClass("form-group");
                $("#edit_form").html(form);
                $.each(data, function(key, value) {
                    var label = $("<label></label>");
                    label.html(key);
                    var input_field = $("<input></input>");
                    input_field.addClass("form-control");
                    input_field.attr("placeholder", key);
                    input_field.attr("value", value);
                    input_field.attr("type", "text");
                    form.append(label);
                    form.append(input_field);
                });
            } else {
                $("#edit_form").html(data.html);
            }
            $("#edit_panel").attr("style", "visibility: visible");
        }
    }, "json");
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
        $("#save_reload_editor_changes").button().removeClass("disabled");
        $("#revert_editor_changes").button().removeClass("disabled");
    });
    $("#save_editor_changes").on("click", function() {
        var formData = new FormData();
        formData.append("yml_file", yaml_editor.getValue());
        $.ajax({
            url: "db_file/" + file_name,
            type: "PUT",
            contentType: false,
            processData: false,
            data: formData,
            success: function() {
		write_message(file_name +" saved!", "success");
            }
        });
    });
    $("#revert_editor_changes").on("click", function() {
        $.get("db_file/" + file_name, function(data) {
            yaml_editor.setValue(data.content);
        }, "json");
    });
}

function write_message(msg, type) {
    $("#message_box").html(msg);
    $("#message_box").removeClass("alert-success alert-warning alert-danger alert-info");
    $("#message_box").addClass("alert-" + type);
}
