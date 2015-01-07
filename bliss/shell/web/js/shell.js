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
    this.cmdline_row = $($.parseHTML('<div style="display:table-row;"></div>'));
    this.cmdline_row.appendTo(table);
    this.cmdline_row.append($('<label style="display:table-cell; width:1%;" class="code-font">&gt;&nbsp;</label>'));
    this.cmdline = $('<input style="width:99%; border:none; display:table-cell;" class="code-font" autofocus></input>');
    this.cmdline.appendTo(this.cmdline_row);
    this.completion_row = $('<div style="display:table-row;"><label style="display:table-cell"></label></div>');
    this.completion_list = $('<ul style="display:table-cell;" class="completion-list"></ul>');
    this.completion_list.appendTo(this.completion_row);
    table.append(this.completion_row);
    this.editor_row = $($.parseHTML('<div style="display:none;"></div>'));
    this.editor_area = $($.parseHTML('<textarea style="width:99%; display:table-cell;"></textarea>'));
    this.editor_area.appendTo(this.editor_row);
    table.append(this.editor_row);
    $('#' + cmdline_div_id).append(table);

    this.output_div = $("#" + shell_output_div_id);
    this.output_div.addClass("code-font");

    this.executing = false;
    this.completion_mode = false;
    this.completion_selected_item_text = '';
    this._completions = [];
    this.session_id = this.get_session_id();
    this.history = JSON.parse(localStorage.getItem(this.session_id + "_shell_commands"));
    if (!this.history)
        this.history = [];
    this.history_index = this.history.length;
    this.current_command = "";
    this.plot = {};

    /* 
       connect to output stream, 
       to get output from server
    */
    this.output_stream = new EventSource('output_stream/' + this.session_id);
    this.output_stream.onmessage = $.proxy(function(e) {
        if (e.data) {
            var output = JSON.parse(e.data);
            if (output.type == 'plot') {
                this.display_plot(output.data);
            } else {
                this.display_output(output.data);
            }
        }
    }, this);

    /*
       this is just for escaping text into valid HTML
       (see _html_escape function)
    */
    this.DOMtext = document.createTextNode("text");
    this.DOMnative = document.createElement("span");
    this.DOMnative.appendChild(this.DOMtext);

    /* 
       jquery override 'this', that's just crazy!
       let methods have the proper 'this' 
    */
    this._cmdline_handle_keydown = $.proxy(this._cmdline_handle_keydown, this);
    this._cmdline_handle_keypress = $.proxy(this._cmdline_handle_keypress, this);

    this.cmdline.keypress(this._cmdline_handle_keypress);
    this.cmdline.keydown(this._cmdline_handle_keydown);
};

Shell.prototype = {
    get_session_id: function() {
        var id;
        $.ajax({
            url: "session",
            dataType: "json",
            async: false,
            success: $.proxy(function(data, status, jqxhr) {
                id = data.session_id;
            }, this)
        });
        return id;
    },

    completion_request: function(text, index) {
        var completion_return;
        $.ajax({
            url: "completion_request",
            dataType: "json",
            data: {
                "text": text,
                "index": index
            },
            async: false,
            success: $.proxy(function(data, status, jqxhr) {
                completion_return = data;
            }, this)
        });
        return completion_return;
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
        if (next_item < 0) {
            selected_item_index = 0;
        } else {
            selected_item_index = (selected_item_index + next_item) % completion_items.length;
        }
        selected_item = $(completion_items[selected_item_index]);
        selected_item.addClass("completion-item-selected");
        this.completion_selected_item_text = selected_item.text();
        this._do_complete(selected_item_index);
    },

    _do_complete: function(completion_index) {
        if (this._completions.length == 0) return;
        var completion = this._completions[completion_index];
        this.cmdline.val(this.current_command.substr(0, this._completion_start) + completion + this.current_command.substr(this._completion_start));
        this.cmdline[0].selectionStart = this._completion_start+completion.length;
        this.cmdline[0].selectionEnd = this.cmdline[0].selectionStart;
    },

    _cmdline_focus: function() {
        var $cmdline = this.cmdline;
        setTimeout(function() { 
          $cmdline.focus();
        }, 10);
    },

    _cmdline_handle_keydown: function(e) {
        if (!this.executing) {
            if (this.completion_mode) {
                if ((e.which == 38) || (e.which == 40)) {
                    /*
                       do not allow up/down arrow keys in
                       completion mode, since it would exit
                       completion mode - it's too easy
                       to press them by mistake
                       while navigating through propositions
                    */
                    e.preventDefault();
                } else if (e.which == 37) {
                    // key left
                    e.preventDefault();
                    this._select_completion_item(-1);
                } else if (e.which == 39) {
                    // key right
                    e.preventDefault();
                    this._select_completion_item(+1);
                } else {
                    this.completion_mode = false;
                    this.completion_list.empty();
                    if ((e.which === 27) || (e.which == 13)) {
                        e.preventDefault();
                    }
                }
            } else {
                if (e.which === 38) {
                    this.history_index--;
                    if (this.history_index <= 0) {
                        this.history_index = 0;
                        this.cmdline.val(this.current_command);
                    } else
                        this.cmdline.val(this.history[this.history_index]);
                } else if (e.which == 40) {
                    this.history_index++;
                    if (this.history_index >= this.history.length) {
                        this.history_index = this.history.length;
                        this.cmdline.val(this.current_command);
                    } else
                        this.cmdline.val(this.history[this.history_index]);
                } else if (e.which == 9) {
                    e.preventDefault();
                    this.current_command = this.cmdline.val();
                    this._completion_start = this.cmdline[0].selectionStart;
                    completion_ret = this.completion_request(this.current_command, this._completion_start);
                    this._completions = completion_ret.completions;
                    var completion_list = completion_ret.possibilities;

                    for (var i = 0; i < completion_list.length; i++) {
                        this.completion_list.append($.parseHTML("<li class='completion-item'>" + completion_list[i] + "</li>"));
                    }

                    this._select_completion_item(0);
                    this.completion_mode = true;
                    this._cmdline_focus();
                } else {
                    this.history_index = this.history.length;
                    this.current_command = this.cmdline.val();
                }
            }
        }
    },

    set_executing: function(executing) {
        this.executing = executing
        if (executing) {
            this.cmdline.addClass("cmdline-executing");
        } else {
            this.cmdline.removeClass("cmdline-executing");
        }
    },

    _cmdline_handle_keypress: function(e) {
        if (e.ctrlKey && e.which === 99) {
            e.preventDefault();
            this.send_abort();
        } else {
            if (this.executing) {
                e.preventDefault();
            } else {
                if (e.which == 13) {
                    if (this.completion_mode) {
                        e.preventDefault();
                    } else {
                        this.execute(this.cmdline.val());
                    }
                }
            }
        }
    },

    execute: function(code) {
        this.set_executing(true);
        this.cmdline.val('');
        this.output_div.append($("<pre>&gt;&nbsp;<i>" + this._html_escape(code) + "</i></pre>"));
        this._execute(code);
    },

    _execute: function(cmd) {
        /* save history */
        this.history.push(cmd);
        this.history_index = this.history.length;
        localStorage[this.session_id + "_shell_commands"] = JSON.stringify(this.history);

        /* make remote call */
        $.ajax({
            error: function(XMLHttpRequest, textStatus, errorThrown) {},
            url: 'command/' + this.session_id,
            type: 'GET',
            success: $.proxy(function(res) {
                if (res.error.length > 0) {
                    if (res.error == "EOF") {
                        /* erase last added echo output */
                        this.output_div.children().last().remove();

                        var cmdline = this.cmdline;
                        var editor_row = this.editor_row;
                        editor_row.css("display", "table-row");
                        var cmdline_row = this.cmdline_row;
                        cmdline_row.css("display", "none"); 
                        var editor_area = this.editor_area;
                        editor_area.val(res.input);
                        var execute = $.proxy(this.execute, this);

                        var editor = CodeMirror.fromTextArea(editor_area[0], {
                            lineNumbers: true,
                            mode: {
                                name: "text/x-cython",
                                version: 2,
                            },
                            autofocus: true,
                            extraKeys: { 'Ctrl-Enter': function() { 
                                              editor.toTextArea();
                                              var code_text = editor_area.val();
                                              editor_row.css("display","none");
                                              cmdline_row.css("display", "table-row");
                                              execute(code_text);
                                          },
                                         'Esc': function() { 
                                              editor.toTextArea(); 
                                              editor_row.css("display","none");
                                              cmdline_row.css("display", "table-row");
                                              cmdline.focus();
                                          } 
                                       }
                        });
                            
                        editor.execCommand("goDocEnd");
                    } else {
                        this.display_output(res.error, true);
                    }
                }
                this.set_executing(false);
                this.cmdline.focus();
            }, this),
            data: {
                "code": cmd,
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
            this.output_div.append($('<pre><font color="red">' + this._html_escape(output) + '</font></pre>'));
        } else {
            var output_pre = $('<pre></pre>');
            output_pre.text(output); 
            output_pre.css({ display: "inline" });
            this.output_div.append(output_pre);
        }
        // scroll to bottom
        this.output_div[0].scrollIntoView(false);
    },

    display_plot: function(data) {
        if (this.plot[data.scan_id]) {
            /* update existing plot */
            var plot = this.plot[data.scan_id];
            if (data.values) {
                plot.data.push(data.values);
                if (plot.obj) {
                    plot.obj.updateOptions({'file': plot.data});
                } else {
                    plot.obj = new Dygraph(plot.div, plot.data, { title: plot.title, labels: plot.labels, legend:"always" });
                }
            } else {
               /* end of scan, free memory */
               delete this.plot[data.scan_id];
            }
        } else {
            /* create new plot */
            this.output_div.append($('<div></div>'));
            var plot_div = this.output_div.children().last()[0]; 
            this.plot[data.scan_id] = { "div": plot_div, 
                                        "data": [], 
                                        "obj": null, 
                                        "title": data.filename, 
                                        "labels": [ data.scan_actuators[0] ].concat(data.counters) };
        }
    },

    send_abort: function() {
        var clear_executing = function() { this.set_executing(false); };

        $.ajax({
            url: 'abort/' + this.session_id,
            type: 'GET',
            dataType: 'json',
            success: clear_executing 
        });
    }

};
