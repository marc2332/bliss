function tree_context_menu(node) {
    var items = {}
    if (node.data.type == 'file') {
	items.add_item = {
	    label: "Add item",
	    icon: "fa fa-star",
	    _disabled: true,
	    action: function() { console.log("add item"); },
	};
    }
    else if (node.data.type == 'folder') {
	items.add_file = {
	    label: "Add file",
	    icon: "fa fa-file",
	    _disabled: true,
	    action: function() { console.log("add file"); },
	};
	items.add_folder = {
	    label: "Add folder",
	    icon: "fa fa-folder",
	    _disabled: true,
	    action: function() { console.log("add folder"); },
	};
    }

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
	_disabled: true,
	action: function() { console.log("delete item"); },
    };
    return items;
}

function tree_populate(container) {
    var tree = {
        core: {
            data: [],
            animation: 0,
            multiple: false
        },
        plugins: ["contextmenu", "search", "dnd"],
	contextmenu: {
	    items: tree_context_menu
	},
	search: {
	    case_insensitive: true,
	    show_only_matches: true,
	}
    };
    var fill_node = function(data, parent_node, level) {
        $.each(data, function(key, value) {
            var new_node = {
                text: key,
                children: [],
                data: {},
                state: {
                    opened: true
                }
            };
            parent_node.push(new_node);
	    node_info = value[0];
	    var node_type = node_info.type;
	    new_node.data.type = node_info.type;
	    new_node.data.path = node_info.path;
	    new_node.icon = node_info.icon;
            fill_node(value[1], new_node.children, level + 1);
        });
    };
    tree_init(container);
    $.get("tree/files", function(data) {
        fill_node(data, tree.core.data, 0);
        container.jstree(tree);
    }, "json");
}

function tree_init(tree) {
    tree.bind("select_node.jstree", on_node_selected);
    tree.bind("select_node.jstree", function(node, data) {
        if (data.node.data.type != "item") {
            $("#clone_item").addClass("disabled");
        } else {
            $("#clone_item").removeClass("disabled");
        }
    });
}

function on_node_selected(ev, data) {
    var node_type = data.node.data.type;
    if (node_type === "file") {
        on_yml_node_selected(ev, data);
    } else {
        on_item_node_selected(ev, data);
    }
}

function on_yml_node_selected(ev, data) {
    $.get("db_file_editor/" + data.node.data.path, function(data) {
        $("#edit_form").empty();
        $("#edit_form_title").html(data.name);
        $("#edit_form_title").parent().attr("style", "visibility: visible");
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
    $.get("objects/" + item_name, function(data) {
        $("#edit_form").empty();
        if (data === null) {
            $("#edit_panel").attr("style", "visibility: hidden");
        } else {
            $("#edit_form_title").html(data.name);
            $("#edit_form_title").parent().attr("style", "visibility: visible");
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
    $("#message_box").removeClass("alert-success alert-warning alert-danger");
    $("#message_box").addClass("alert-" + type);
}
