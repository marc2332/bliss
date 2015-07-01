function populate_tree(container) {
  var tree = { core: {
                 data: [ ],
                 animation: 0,
                 multiple: false },
	       plugins : [ ] };

  var fill_node = function(data, node, level) {
    $.each(data, function(key, value) {
        var new_node = { text: key,
			 children: [],
			 data: {},
			 state: { opened: true } };

        node.push(new_node);
        if (key.match("yml$")=="yml") {
 	   new_node.icon = "glyphicon glyphicon-file";
	   new_node.data.type = "yml";
        }

        fill_node(value, new_node.children, level + 1);

        if (new_node.icon === undefined) {
           if (new_node.children.length > 0) {
              new_node.icon = 'glyphicon glyphicon-folder-open';
              new_node.data.type = "folder";
           } else {
              new_node.icon = 'glyphicon glyphicon-star';
              new_node.data.type = "item";
           }
        }
    });
  };

  init_tree(container);

  $.get("objects", function(data) {
    fill_node(data, tree.core.data, 0);
    container.jstree(tree)
  }, "json");
}

function init_tree(tree) {
  tree.bind("select_node.jstree", function(ev, data) {
  var node_name = data.node.text;

  $.get("objects/"+node_name, function(data) {
    $("#edit_form").empty();
    if (data === null) {
      $("#edit_panel").attr("style", "visibility: hidden");
    }
    else {
      if (data.html === undefined) {
        $("#edit_form_title").html(data.name)
        $("#edit_form_title").parent().attr("style", "visibility: visible");
        var form = $("<form></form>");
        $("#edit_form").html(form);
        $.each(data, function(key, value) {
          var label = $("<label></label>");
          label.html(key);
          var input_field = $("<input></input>");
          input_field.attr("class", "form-control");
          input_field.attr("placeholder", key);
          input_field.attr("value", value);
          input_field.attr("type", "text");
          form.append(label);
          form.append(input_field);
        });
      } else {
        $("#edit_form_title").parent().attr("style", "visibility: hidden");
        $("#edit_form").html(data.html);
      }
      $("#edit_panel").attr("style", "visibility: visible");
    }
    }, "json");
  });

  tree.bind("select_node.jstree", function(node, data) {
    if (data.node.data.type != 'item') {
      $("#clone_item").addClass("disabled");
    }
    else {
      $("#clone_item").removeClass("disabled");
    }
  });
}
