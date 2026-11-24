/* Melhoria progressiva do formulário de doação (Specs 08 e 09 / ADR 0006). */
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    const selectConservacao = document.querySelector("[data-conservacao-select]");
    const blocoRefrigeracao = document.getElementById("bloco-refrigeracao");
    const avisoEmbalagem = document.getElementById("aviso-embalagem-violada");
    const avisoControleEspecial = document.getElementById("aviso-controle-especial");
    const radiosEmbalagem = document.querySelectorAll('input[name="embalagem_integra"]');
    const radiosControle = document.querySelectorAll('input[name="controle_especial"]');

    function atualizarBlocoRefrigeracao() {
      if (!selectConservacao || !blocoRefrigeracao) {
        return;
      }
      const ehRefrigerado = selectConservacao.value === "refrigerado";
      blocoRefrigeracao.classList.toggle("d-none", !ehRefrigerado);
    }

    function atualizarAvisosBloqueio() {
      if (avisoEmbalagem) {
        const selecionada = document.querySelector('input[name="embalagem_integra"]:checked');
        avisoEmbalagem.classList.toggle("d-none", !selecionada || selecionada.value !== "nao");
      }
      if (avisoControleEspecial) {
        const selecionado = document.querySelector('input[name="controle_especial"]:checked');
        avisoControleEspecial.classList.toggle("d-none", !selecionado || selecionado.value !== "sim");
      }
    }

    if (selectConservacao) {
      selectConservacao.addEventListener("change", atualizarBlocoRefrigeracao);
      atualizarBlocoRefrigeracao();
    }

    radiosEmbalagem.forEach(function (radio) {
      radio.addEventListener("change", atualizarAvisosBloqueio);
    });
    radiosControle.forEach(function (radio) {
      radio.addEventListener("change", atualizarAvisosBloqueio);
    });
    atualizarAvisosBloqueio();
  });
})();
