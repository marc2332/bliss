var anchors = Array.from(document.getElementsByClassName("md-nav__link"));
anchors.forEach(function(anchor) {
	var sep = anchor.innerText.indexOf("|");
	if (sep != -1) {
		anchor.href = document.location.origin + "/" + anchor.innerText.substring(sep + 1, anchor.innerText.length);
		anchor.innerText = anchor.innerText.substring(0,sep);
	}
	if (anchor.innerText.indexOf("\uD83D\uDDD7") != -1) { // &#x1F5D7; = "new window" char, see http://www.fileformat.info/info/unicode/char/1f5d7/index.htm
		anchor.target = "_blank";
	}
});

