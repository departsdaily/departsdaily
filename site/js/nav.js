/* =====================================================================
   DEPARTS DAILY — canonical site nav.
   One list of links, identical on every page, with the current page
   marked. Previously each page carried its own hand-written nav, so the
   labels changed as you moved around the site.
   Loads before paint on every page; no dependencies.
   ===================================================================== */
(function () {
  var LINKS = [
    { href: "index.html",     label: "DEAL BOARD"  },
    { href: "index.html#search", label: "FARE FINDER" },
    { href: "guides.html",    label: "CITY GUIDES" },
    { href: "gear.html",      label: "GEAR"        }
  ];

  var path  = location.pathname;
  var deep  = /\/destinations\//.test(path);      // one level down
  var prefix = deep ? "../" : "";
  var file  = path.split("/").pop() || "index.html";

  function isCurrent(l) {
    var target = l.href.split("#")[0];
    if (deep) return l.href === "guides.html";     // a guide page IS city guides
    if (file === "search.html") return l.href === "index.html#search";
    if (target === "index.html") return (file === "index.html" || file === "")
      && l.href.indexOf("#") < 0;
    return file === target;
  }

  document.addEventListener("DOMContentLoaded", function () {
    var nav = document.querySelector(".hnav");
    if (!nav) return;
    nav.innerHTML = LINKS.map(function (l) {
      var cur = isCurrent(l);
      return '<a href="' + prefix + l.href + '"' +
             (cur ? ' aria-current="page"' : "") + ">" + l.label + "</a>";
    }).join("");
  });
})();
