function populate_tree(container) {
    var tree = {
        core: {
            data: [],
            animation: 0,
            multiple: false
        },
        plugins: []
    };
    var fill_node = function(data, node, level) {
        $.each(data, function(key, value) {
            var new_node = {
                text: key,
                children: [],
                data: {},
                state: {
                    opened: true
                }
            };
            node.push(new_node);
            if (key.match("yml$") == "yml") {
                new_node.icon = "glyphicon glyphicon-file";
                new_node.data.type = "yml";
                new_node.data.path = value[0];
            }
            fill_node(value[1], new_node.children, level + 1);
            if (new_node.icon === undefined) {
                if (new_node.children.length > 0) {
                    new_node.icon = "glyphicon glyphicon-folder-open";
                    new_node.data.type = "folder";
                } else {
                    new_node.icon = "glyphicon glyphicon-star";
                    new_node.data.type = "item";
                }
            }
        });
    };
    init_tree(container);
    $.get("objects", function(data) {
        fill_node(data, tree.core.data, 0);
        container.jstree(tree);
    }, "json");
}

function init_tree(tree) {
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
    if (node_type === "yml") {
        on_yml_node_selected(ev, data);
    } else if (node_type === "item") {
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
                alert("File saved!");
            }
        });
    });
    $("#revert_editor_changes").on("click", function() {
        $.get("db_file/" + file_name, function(data) {
            yaml_editor.setValue(data.content);
        }, "json");
    });
}
