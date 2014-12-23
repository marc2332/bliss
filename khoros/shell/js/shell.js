/*
var askForLogMessages = function() {
    $.ajax({
        error: function(XMLHttpRequest, textStatus, errorThrown) {},
        url: 'log_msg_request',
        type: 'GET',
        success: function(msg) {
            jQuery("#logger:first").append("<p>" + msg + "</p>");
        },
        complete: function() {
            askForLogMessages();
        },
        data: {
            "client_id": term.session_id
        },
        dataType: 'json'
    });
}
*/

function Shell(cmdline_div_id, shell_output_div_id) {
    var table = $('<div style="width:100%; display:table;"></div>');
    var cmdline_row = $($.parseHTML('<div style="display:table-row;"></div>'));
    cmdline_row.appendTo(table);
    cmdline_row.append($('<label style="display:table-cell; width:1%;" class="code-font">&gt;&nbsp;</label>'));
    this.cmdline = $('<input style="width:99%; border:none; display:table-cell;" class="code-font"></input>');
    this.cmdline.appendTo(cmdline_row);
    this.completion_row = $('<div style="display:table-row;"><label style="display:table-cell"></label></div>');
    this.completion_list = $('<ul style="display:table-cell;" class="completion-list"></ul>');
    this.completion_list.appendTo(this.completion_row);
    table.append(this.completion_row);
    this.editor_row = $($.parseHTML('<div style="display:none;"></div>'));
    this.editor_area = $($.parseHTML('<textarea style="width:99%; display:table-cell;"></textarea>'));
    this.editor_area.appendTo(this.editor_row);
    table.append(this.editor_row);
    $('#' + cmdline_div_id).append(table);

    this.output_div = $("#"+shell_output_div_id);
    this.output_div.addClass("code-font");

    this.executing = false;
    this.completion = false;
    this.completion_selected_item_text = '';
    this.session_id = this.get_session_id();
    this.output_stream = new EventSource('output_stream/'+this.session_id);
    this.output_stream.addEventListener('message', $.proxy(function(e) { this.display_output(e.data); }, this), false);

    /*
       this is just for escaping text into valid HTML
       (see _html_escape function)
    */
    this.DOMtext = document.createTextNode("text");
    this.DOMnative = document.createElement("span");
    this.DOMnative.appendChild(this.DOMtext);

    /* 
       jquery override 'this', that's just crazy!
       let methods having the proper 'this' 
    */
    this._cmdline_handle_keydown = $.proxy(this._cmdline_handle_keydown, this);
    this._cmdline_handle_keypress = $.proxy(this._cmdline_handle_keypress, this);

    this.cmdline.keypress(this._cmdline_handle_keypress);
    this.cmdline.keydown(this._cmdline_handle_keydown);
    this.cmdline.focus();

    
};

Shell.prototype = {
    get_session_id: function() {
      var id;
      $.ajax({ url: "session",
               dataType: "json",
               async: false,
               success: $.proxy(function(data, status, jqxhr) {
                 id = data.session_id;   
               }, this)
             });
      return id;
    },

    _select_completion_item: function(next_item) {
       var completion_items = this.completion_list.children();
       var selected_item_index = 0;
       var selected_item = null;

       completion_items.each(function(i, j) {
           if ($(this).hasClass("completion-item-selected")) {
                selected_item_index = i;
                $(this).removeClass("completion-item-selected");
           }
           $(this).addClass("completion-item");
       });
       selected_item_index = selected_item_index + next_item;
       if (selected_item_index < 0)
           selected_item_index = 0; 
       if (selected_item_index >= completion_items.length) 
           selected_item_index = 0;
       selected_item = $(completion_items[selected_item_index]);       
       selected_item.addClass("completion-item-selected");
       this.completion_selected_item_text = selected_item.text();
    },

    _cmdline_handle_keydown: function(e) {
        if (!this.executing) {
            if (this.completion) {
                if (e.which === 27) {
                    this.completion = false;
                    this.completion_list.empty();
                } else if (e.which == 37) {
                    // key left
                    e.preventDefault();
                    this._select_completion_item(-1);
                } else if (e.which == 39) {
                    // key right
                    e.preventDefault();
                    this._select_completion_item(+1);
                }
            } else {
                if (e.which === 38) {
                    alert("KEY UP");
                } else if (e.which == 40) {
                    alert("KEY DOWN");
                } else if (e.which == 9) {
                    e.preventDefault();
                    for (var i = 0; i < 50; i++) {
                        if (i == 0) {
                            klass = 'completion-item-selected';
                        } else {
                            klass = 'completion-item';
                        }

                        this.completion_list.append($.parseHTML("<li class='" + klass + "'>BLA" + (i + 1) + "</li>"));
                     }
                     this.completion = true;
                 }
             }
        }
    },

    _cmdline_handle_keypress: function(e) {
        if (e.ctrlKey && e.which === 99) {
            this.executing = false;
            alert("CTRL-C");
        } else {
            if (this.executing) {
                e.preventDefault();
            } else {
                if (e.which == 13) {
                    if (this.completion) {
                      e.preventDefault();
                      alert(this.completion_selected_item_text); 
                    } else {
                      this.executing = true;
                      var code = this.cmdline.val();
                      this.cmdline.val('');
                      this.output_div.append($("<p>&gt;&nbsp;<i>"+this._html_escape(code)+"</i></p>"));
                      this.execute(code);
                      
                    }
                }
            }
        }
    },

    execute: function(cmd, multiline) {
    $.ajax({
        error: function(XMLHttpRequest, textStatus, errorThrown) {},
        url: 'command/'+this.session_id,
        type: 'GET',
        success: $.proxy(function(res) {
            if (res.error.length > 0) {
                if (res.error == "EOF") {
                    /*
                    term.pause();
                    term_div.append("<textarea id='editor'>" + res.input + "</textarea>");
                    var editor = CodeMirror.fromTextArea(document.getElementById("editor"), {
                        lineNumbers: true,
                        mode: {
                            name: "text/x-cython",
                            version: 2,
                        },
                        autofocus: true
                    });
                    editor.execCommand("goDocEnd");
                    term_div.append("<button id='exec_code' type='button'>Execute</button><button id='close_code' type='button'>Close</button>");
                    $("#close_code").click(function() {
                        editor.toTextArea();
                        $("#editor").remove();
                        $("#exec_code").remove();
                        $("#close_code").remove();
                        createTerminal(term_div, term.session_id, true);
                    });
                    $("#exec_code").click(function() {
                        editor.toTextArea();
                        var code_text = $("#editor").val();
                        $("#editor").remove();
                        $("#exec_code").remove();
                        $("#close_code").remove();
                        createTerminal(term_div, term.session_id, true);
                        term.echo(code_text);
                        fireOffCmd(code_text, true);
                    });*/
                    return;
                } else {
                    this.display_output(res.error, true);
                }
            }
            this.executing = false;
        }, this),
        data: {
            "code": cmd,
            "multiline": multiline
        },
        dataType: 'json'
    });
},

_html_escape: function(text) {
    this.DOMtext.nodeValue = text;
    return this.DOMnative.innerHTML; 
},

display_output: function(output, error) {
       if (error) {
         this.output_div.append($('<pre><font color="red">'+this._html_escape(output)+'</font></pre>'));
       } else {
         this.output_div.append($('<pre>'+this._html_escape(output)+'</pre>'));
       }
},

abort: function() {
    $.ajax({
        url: 'abort/'+this.session_id,
        type: 'GET',
        async: false,
        dataType: 'json'
    });
}

};
