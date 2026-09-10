// Mostra o campo "Conte um pouco mais" quando a origem é "Outro".
(function () {
  "use strict";
  document.querySelectorAll("select[name='referral_source']").forEach(function (select) {
    var form = select.closest("form") || document;
    var extra =
      form.querySelector("[data-origem-outro]") || document.getElementById("campo-outro");
    if (!extra) return;
    var input = extra.querySelector("input, textarea");

    function sync() {
      var mostrar = select.value === "outro";
      extra.hidden = !mostrar;
      if (input) input.required = mostrar;
    }
    select.addEventListener("change", sync);
    sync();
  });
})();
