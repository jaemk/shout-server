


document.addEventListener('DOMContentLoaded', function() {
    // stream dump section
    var streamDataTable = document.getElementById('stream-data-table');

    // message block below stream section
    var streamMsg = document.getElementById('stream-message');

    var sourceCommand = document.getElementById('source-command');

    // autoscroll div
    var autoScrollDiv = document.getElementById("auto-scroll");
    var autoScrollOff = document.getElementById("auto-scroll-off");
    var autoScrollOn  = document.getElementById("auto-scroll-on");
    var autoScroll = true;

    autoScrollDiv.addEventListener('click', function() {
        autoScroll = !autoScroll;
        if (autoScroll) {
            autoScrollOn.className = '';
            autoScrollOff.className = 'hidden';
        } else {
            autoScrollOn.className = 'hidden';
            autoScrollOff.className = '';
        }
    })

    var streamId = document.getElementById('stream-id').value;
    var sock = new WebSocket('ws://' + location.host + '/api/ws');
    var connectTimeout = 500;  // ms
    sock.onmessage = sockHandler;

    function send(obj) {
        sock.send(JSON.stringify(obj));
    }

    var lineNo = 1;
    function sockHandler(event) {
        var data = JSON.parse(event.data);
        //console.log(data);
        if (data.subscribe === 'ok') {
            console.log('Subscribe confirmed');
            streamMsg.style.cssText = "";  // make sure it's not hidden
            streamMsg.innerText = "Connected!";
            if (data.source_command) {
                sourceCommand.innerText = data.source_command;
            }
        } else if (data.error) {
            streamMsg.style.cssText = "";  // make sure it's not hidden
            streamMsg.innerText = '[' + data.error.short + '] ' + data.error.msg;
        } else {
            streamMsg.style.cssText = "display: none;";

            var newRow = document.createElement("div");
            newRow.className = "stream-data-row";
            streamDataTable.appendChild(newRow);

            var newGutterCell = document.createElement("div");
            newGutterCell.className = "stream-data-gutter";
            newRow.appendChild(newGutterCell);

            var newGutterLine = document.createElement("code");
            newGutterLine.className = "code-line";
            newGutterLine.innerText = "" + lineNo;
            lineNo++;
            newGutterCell.appendChild(newGutterLine);

            var newStreamCell = document.createElement("div");
            newStreamCell.className = "stream-data";
            newRow.appendChild(newStreamCell);

            var newLine = document.createElement("pre");
            newLine.className = "code-line";
            newLine.innerText = data.payload;
            newStreamCell.appendChild(newLine);

            if (autoScroll) {
                newRow.scrollIntoView();
            }
        }
    }


    console.log("Waiting for socket connection...");
    function trySubscribe(timeout) {
        if (sock.readyState === sock.OPEN) {
            console.log("Socket connection confirmed!");
            console.log("Subscribing to: " + streamId);
            send({subscribe: streamId});
        } else {
            setTimeout(trySubscribe, timeout + 500);
        }
    }
    setTimeout(function() { trySubscribe(connectTimeout); }, connectTimeout);

});
