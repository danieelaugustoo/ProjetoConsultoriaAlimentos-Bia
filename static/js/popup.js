// Pop-up de cadastro: aparece uma vez na primeira visita.
// "Agora não" ou enviar o formulário marca como dispensado (localStorage).
(function () {
  "use strict";
  var CHAVE = "bv_popup_cadastro";
  var overlay = document.getElementById("popup-cadastro");
  if (!overlay) return;

  var jaResolvido = false;
  try {
    jaResolvido = localStorage.getItem(CHAVE) === "1";
  } catch (e) {}

  function marcar() {
    try {
      localStorage.setItem(CHAVE, "1");
    } catch (e) {}
  }

  function fechar() {
    overlay.hidden = true;
    document.body.style.overflow = "";
    marcar();
  }

  if (!jaResolvido) {
    // pequeno atraso para não competir com o carregamento da página
    setTimeout(function () {
      overlay.hidden = false;
      document.body.style.overflow = "hidden";
    }, 1200);
  }

  overlay.querySelectorAll("[data-popup-dispensar]").forEach(function (btn) {
    btn.addEventListener("click", fechar);
  });

  overlay.addEventListener("click", function (ev) {
    if (ev.target === overlay) fechar();
  });

  document.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape" && !overlay.hidden) fechar();
  });

  // Ao enviar, marca como resolvido (a navegação leva para a página de sucesso).
  var form = overlay.querySelector("form");
  if (form) form.addEventListener("submit", marcar);
})();
