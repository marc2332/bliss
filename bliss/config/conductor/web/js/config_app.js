function populate_tree(container) {
  var root = { "text": "", children: [] }
  var tree = { "core": { "data": [ ] } };

  var fill_node = function(data, node) {
    $.each(data, function(key, value) {
        var new_node = { "text": key, "children": [] };
        node.push(new_node);
        if (key.match("yml$")=="yml") {
 	   new_node.icon = "glyphicon glyphicon-file";
        }

        fill_node(value, new_node.children);

        if (new_node.icon === undefined) {
           if (new_node.children.length > 0) {
              new_node.icon = 'glyphicon glyphicon-folder-open';
           } else {
              new_node.icon = 'glyphicon glyphicon-star';  
           }
        }  
    });
  };

  $.get("objects", function(data) {
    fill_node(data, tree.core.data);
    container.jstree(tree);
  }, "json");
}
