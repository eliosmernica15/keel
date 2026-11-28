/* Tiny CSP-safe fallback for the short product route indexes.
   The <meta http-equiv="refresh"> in each stub redirects without JS; this
   external script does the same with location.replace so the redirect is not
   added to browser history. No inline script is used (site CSP forbids it). */
(function () {
  "use strict";
  var target = document.body && document.body.getAttribute("data-redirect");
  if (target && /^\/[A-Za-z0-9\/_-]*$/.test(target)) {
    location.replace(target);
  }
}());
