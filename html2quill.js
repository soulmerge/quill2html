var jsdom = require("jsdom");

/* global process */

jsdom.env({
    html: '<div id="editor-container"></div>',
    scripts: [
        'https://cdnjs.cloudflare.com/ajax/libs/webcomponentsjs/0.7.22/MutationObserver.js',
        'https://cdn.quilljs.com/1.0.4/quill.js'],
    onload: function (window) {
        var document = window.document;
        // fake getSelection
        // https://github.com/tmpvar/jsdom/issues/317
        document.getSelection = function() { 
            return { 
                getRangeAt: function() {}
            };
        }; 

        var container = window.document.getElementById("editor-container");
        var quill = new window.Quill(container, {});
        var buffer = '';
        process.stdin.resume();
        process.stdin.setEncoding('utf8');
        process.stdin.on('data', function(chunk) {
            buffer += chunk;
            if (buffer.indexOf('\0') < 0) {
                return;
            }
            var parts = buffer.split('\0');
            var html = parts[0];
            buffer = parts[1];
            quill.getModule('clipboard').dangerouslyPasteHTML(html);
            console.log(JSON.stringify(quill.getContents()) + '\0');
        });
    },
});
