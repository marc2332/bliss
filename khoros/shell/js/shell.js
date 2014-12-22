var term;
var term_div;

var fireOffCmd = function(cmd, multiline) {
    $.ajax({
        error: function(XMLHttpRequest, textStatus, errorThrown) {},
        url: 'command',
        type: 'GET',
        success: function(res) {
            if (res.error.length > 0) {
                if (res.error == "EOF") {
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
                    });
                    return;
                } else {
                    term.error(res.error);
                }
            }
            term.executing = false;
            term.set_prompt("> ");
        },
        data: {
            "client_id": term.session_id,
            "code": cmd,
            "multiline": multiline
        },
        dataType: 'json'
    });
}

var askForOutput = function() {
    $.ajax({
        error: function(XMLHttpRequest, textStatus, errorThrown) {},
        url: 'output_request',
        type: 'GET',
        success: function(output) {
            term.echo(output);
        },
        complete: function() {
            askForOutput();
        },
        data: {
            "client_id": term.session_id
        },
        dataType: 'json'
    });
}

var abortExecution = function() {
    $.ajax({
        url: 'abort',
        type: 'GET',
        async: false,
        data: {
            "client_id": term.session_id
        },
        dataType: 'json'
    });
}

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


function createTerminal(parent_div, session_id, dontaskforoutput) {
    term_div = parent_div;
    parent_div.append("<div></div>")
    term = parent_div.children().last().terminal(
        function(command, term) {
            if (command != '') {
                term.executing = true;
                term.set_prompt("");
                fireOffCmd(command);
            }
        }, {
            greetings: '',
            prompt: '> ',
            //height: 600,
            keypress: function(e, term) {
                if (term.paused()) return true;

                if (e.ctrlKey && e.which === 99) { // CTRL+C
                    abortExecution();
                    return false;
                }
                if (term.executing) return false;
                else return true;
            },
            tabcompletion: true,
            completion: function(term, string, callback) {
                term.disable();
                $.ajax({
                    error: function(XMLHttpRequest, textStatus, errorThrown) {},
                    url: 'completion_request',
                    type: 'GET',
                    success: function(res) {
                        term.enable();
                        callback(res.possibilities);
                    },
                    data: {
                        "client_id": term.session_id,
                        "text": string
                    },
                    dataType: 'json'
                });
            }
        });

    term.executing = false;
    term.session_id = session_id;

    if (!dontaskforoutput) askForOutput();
};

function Shell(cmdline_div_id, shell_output_div_id) {
    var table = $('<div style="width:100%; display:table;"></div>');
    var cmdline_row = $($.parseHTML('<div style="display:table-row;"></div>'));
    cmdline_row.appendTo(table);
    cmdline_row.append($('<label style="display:table-cell; width:1%;" class="cmdline-font">&gt;&nbsp;</label>'));
    this.cmdline = $('<input style="width:99%; border:none; display:table-cell;" class="cmdline-font"></input>');
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

    this.executing = false;
    this.completion = false;

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
    _cmdline_handle_keydown: function(e) {
        if (!this.executing) {
            if (this.completion) {
                if (e.which === 27) {
                    this.completion = false;
                    this.completion_list.empty();
                } else {
                    e.preventDefault();
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
                    this.executing = true;
                    alert("ENTER");
                }
            }
        }
    }
};