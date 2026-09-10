// Mostra/esconde o campo "Conte um pouco mais" conforme a opção "Outro".
(function () {
  "use strict";
  var select = document.getElementById("referral_source");
  var campoOutro = document.getElementById("campo-outro");
  if (!select || !campoOutro) return;

  var input = campoOutro.querySelector("input, textarea");

  function sincronizar() {
    var mostrar = select.value === "outro";
    campoOutro.hidden = !mostrar;
    if (input) input.required = mostrar;
  }

  select.addEventListener("change", sincronizar);
  sincronizar();
})();
