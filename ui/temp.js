
<html>
<head><title>SAMP Table Display</title></head>

<body>
<script src="lib/samp.js"></script>
<script src="lib/json2.js"></script>
<script src="lib/flxhr/flXHR.js"></script>
<script>
var baseUrl = window.location.href.toString().replace(new RegExp("[^/]*$"), "");
var hTbodyNode;
var tableId;
var tableUrl;

var cc = new samp.ClientTracker();
var callHandler = cc.callHandler;
callHandler["samp.app.ping"] = function(senderId, message, isCall) {
    if (isCall) {
        return {text: "ping to you, " + cc.getName(senderId)};
    }
};
var showTableError = function(txt) {
    var rnode = document.getElementById("resultPanel");
    rnode.innerHTML = "";
    var pnode = document.createElement("p");
    pnode.appendChild(document.createTextNode(txt));
    rnode.appendChild(pnode);
};
var getTextContent = function(node) {
    var txt = "";
    var n;
    for (n = node.firstChild; n; n = n.nextSibling) {
        if (n.nodeType === 3 ||     // text
            n.nodeType === 4)    {  // CDATA section
            txt = txt + n.data;
        }
    }
    return txt;
};
var rowClickAction = function(irow, trNode) {
   return function() {
       var oldColor = trNode.style.backgroundColor;
       trNode.style.backgroundColor = "#0f0";
       window.setTimeout(function() {trNode.style.backgroundColor = oldColor;},
                         500);
       var message =
           new samp.Message("table.highlight.row",
                            {"table-id": tableId,
                             "url": tableUrl,
                             "row": "" + irow});
       connector.connection.notifyAll([message]);
   }
};
var displayVotable = function(xml) {
    var vDocEl = xml.documentElement;
    // showTableError("Got XML doc " + docEl.tagName);
    var vTableEl = vDocEl.getElementsByTagName("TABLE")[0];
    var vFieldEls = vTableEl.getElementsByTagName("FIELD");
    var vTrEls = vTableEl.getElementsByTagName("TR");
    var ncol = vFieldEls.length;
    var nrow = vTrEls.length;
    var hTableNode = document.createElement("table");
    hTableNode.setAttribute("border", 1);
    var hTheadNode = document.createElement("thead");
    var hTrNode = document.createElement("tr");
    var ic;
    var ir;
    var hThNode;
    for (ic = 0; ic < ncol; ic++) {
        hThNode = document.createElement("th");
        hThNode.setAttribute("nowrap", "nowrap");
        hThNode.appendChild(document.createTextNode(vFieldEls[ic].
                                                    getAttribute("name")));
        hTrNode.appendChild(hThNode);
    }
    hTheadNode.appendChild(hTrNode);
    hTableNode.appendChild(hTheadNode);

    hTbodyNode = document.createElement("tbody");
    var vTdEls;
    var hTdNode;
    for (ir = 0; ir < nrow; ir++) {
        vTdEls = vTrEls[ir].getElementsByTagName("TD");
        hTrNode = document.createElement("tr");
        for (ic = 0; ic < ncol; ic++) {
            hTdNode = document.createElement("td");
            hTdNode.setAttribute("nowrap", "nowrap");
            hTdNode.appendChild(document.
                                createTextNode(getTextContent(vTdEls[ic])));
            hTrNode.appendChild(hTdNode);
        }
        hTrNode.onclick = rowClickAction(ir, hTrNode);
        hTbodyNode.appendChild(hTrNode);
    }
    hTableNode.appendChild(hTbodyNode);

    var hResultNode = document.getElementById("resultPanel");
    hResultNode.innerHTML = "";
    hResultNode.appendChild(hTableNode);
};
callHandler["table.load.votable"] = function(senderId, message, isCall) {
    var params = message["samp.params"];
    var origUrl = params["url"];
    var proxyUrl = cc.connection.translateUrl(origUrl);
    var xhr = samp.XmlRpcClient.createXHR();
    var e;
    xhr.open("GET", proxyUrl);
    xhr.onload = function() {
        var xml = xhr.responseXML;
        if (xml) {
            try {
                displayVotable(xml);
                tableId = params["table-id"];
                tableUrl = origUrl;
            }
            catch (e) {
                showTableError("Error displaying table:\n" +
                               e.toString());
            }
        }
        else {
            showTableError("No XML response");
        }
    };
    xhr.onerror = function(err) {
        showTableError("Error getting table " + origUrl + "\n" +
                       "(" + err + ")");
    };
    xhr.send(null);
};
callHandler["table.highlight.row"] = function(senderId, message, isCall) {
    var params = message["samp.params"];
    highlightRows(params["table-id"], params["url"], [params["row"]]);
};
callHandler["table.select.rowList"] = function(senderId, message, isCall) {
    var params = message["samp.params"];
    highlightRows(params["table-id"], params["url"], params["row-list"]);
};
var highlightRows = function(tid, turl, irows) {
    if (tid === tableId || turl === tableUrl) {
        var ix;
        var rowFlags = {};
        for (ix = 0; ix < irows.length; ix++) {
            rowFlags[1*irows[ix]] = true;
        }
        var hTrNodes = hTbodyNode.getElementsByTagName("TR");
        var ir;
        for (ir = 0; ir < hTrNodes.length; ir++) {
            hTrNodes[ir].style.backgroundColor =
                (ir in rowFlags) ? "#bde" : "#fff";
        }
    }
}
var meta = {
    "samp.name": "TableDisplay",
    "samp.description":
        "JavaScript-based Web Profile client to display and interact with " +
        "a small VOTable",
    "samp.icon.url": baseUrl + "clientIcon.gif"
};
var subs = cc.calculateSubscriptions();
var connector = new samp.Connector("Table Display", meta, cc, subs);

connector.onunreg = function() {
    showTableError("");
}
onload = function() {
    document.getElementById("regPanel").
             appendChild(connector.createRegButtons());
};
onunload = function() {
    connector.unregister();
};

</script>

<p>This client can receive a VOTable (TABLEDATA only) from another SAMP client
(<tt>table.load.votable</tt>) and receive row highlight messages from it
(<tt>table.highlight.row</tt>, <tt>table.select.rowList</tt>).
If you click on a row in the loaded table, it will broadcast a
<tt>table.highlight.row</tt> message.
</p>
<p>This is a proof of concept only - it is not very robust or scalable.
You probably shouldn't try to send a table with more than a few hundred rows.
</p>

<div id="regPanel"></div>
<h3>Table</h3>
<div id="resultPanel"></div>

</body>
</html>
