/* Melhoria progressiva para telas de ponto de coleta (ADR 0006 / ADR 0018).
 * Todo o fluxo permanece funcional sem JavaScript; validações reais ocorrem no servidor.
 */

(function () {
  "use strict";

  function somenteDigitos(valor) {
    return (valor || "").replace(/\D/g, "");
  }

  function aplicarMascaraCnpj(valor) {
    var d = somenteDigitos(valor).slice(0, 14);
    if (d.length <= 2) return d;
    if (d.length <= 5) return d.slice(0, 2) + "." + d.slice(2);
    if (d.length <= 8) return d.slice(0, 2) + "." + d.slice(2, 5) + "." + d.slice(5);
    if (d.length <= 12) {
      return d.slice(0, 2) + "." + d.slice(2, 5) + "." + d.slice(5, 8) + "/" + d.slice(8);
    }
    return (
      d.slice(0, 2) +
      "." +
      d.slice(2, 5) +
      "." +
      d.slice(5, 8) +
      "/" +
      d.slice(8, 12) +
      "-" +
      d.slice(12)
    );
  }

  function aplicarMascaraCep(valor) {
    var d = somenteDigitos(valor).slice(0, 8);
    if (d.length <= 5) return d;
    return d.slice(0, 5) + "-" + d.slice(5);
  }

  function aplicarMascaraTelefone(valor) {
    var d = somenteDigitos(valor).slice(0, 11);
    if (d.length === 0) return "";
    if (d.length <= 2) return "(" + d;
    if (d.length <= 6) return "(" + d.slice(0, 2) + ") " + d.slice(2);
    if (d.length <= 10) {
      return "(" + d.slice(0, 2) + ") " + d.slice(2, 6) + "-" + d.slice(6);
    }
    return "(" + d.slice(0, 2) + ") " + d.slice(2, 7) + "-" + d.slice(7);
  }

  function inicializarMascaras() {
    var campos = document.querySelectorAll("[data-mascara]");
    campos.forEach(function (campo) {
      var tipo = campo.getAttribute("data-mascara");
      campo.addEventListener("input", function () {
        if (tipo === "cnpj") {
          campo.value = aplicarMascaraCnpj(campo.value);
        } else if (tipo === "cep") {
          campo.value = aplicarMascaraCep(campo.value);
        } else if (tipo === "celular") {
          campo.value = aplicarMascaraTelefone(campo.value);
        }
      });
    });
  }

  function inicializarConsultaCep() {
    var campoCep = document.getElementById("id_cep");
    if (!campoCep) return;

    var urlBase = campoCep.getAttribute("data-cep-url-base");
    if (!urlBase) return;

    var statusEl = document.getElementById("cep-status-msg");
    var campoLogradouro = document.getElementById("id_logradouro");
    var campoBairro = document.getElementById("id_bairro");
    var campoMunicipio = document.getElementById("id_municipio");
    var campoEstado = document.getElementById("id_estado");
    var campoNumero = document.getElementById("id_numero");
    var ultimoCep = "";

    function definirStatus(texto, tipo) {
      if (!statusEl) return;
      statusEl.textContent = texto;
      statusEl.className = "remed-hint mt-1";
      if (tipo === "erro") statusEl.classList.add("text-danger");
      if (tipo === "sucesso") statusEl.classList.add("text-success");
    }

    function consultar() {
      var digitos = somenteDigitos(campoCep.value);
      if (digitos.length !== 8 || digitos === ultimoCep) return;
      ultimoCep = digitos;
      definirStatus("Buscando endereço pelo CEP...", "info");

      fetch(urlBase.replace("00000000", digitos), {
        method: "GET",
        headers: { Accept: "application/json" },
        credentials: "same-origin",
      })
        .then(function (resp) {
          return resp.json().then(function (dados) {
            return { ok: resp.ok, dados: dados };
          });
        })
        .then(function (res) {
          if (!res.ok) {
            definirStatus(
              (res.dados && res.dados.erro) ||
                "Não foi possível consultar o CEP. Preencha o endereço manualmente.",
              "erro"
            );
            return;
          }
          var d = res.dados;
          if (campoLogradouro && d.logradouro) campoLogradouro.value = d.logradouro;
          if (campoBairro && d.bairro) campoBairro.value = d.bairro;
          if (campoMunicipio && d.municipio) campoMunicipio.value = d.municipio;
          if (campoEstado && d.estado) campoEstado.value = d.estado;
          definirStatus("Endereço preenchido pelo CEP. Informe o número e complemento.", "sucesso");
          if (campoNumero && !campoNumero.value) campoNumero.focus();
        })
        .catch(function () {
          definirStatus(
            "Consulta de CEP indisponível no momento. Preencha o endereço manualmente.",
            "erro"
          );
        });
    }

    campoCep.addEventListener("blur", consultar);
    campoCep.addEventListener("input", function () {
      if (somenteDigitos(campoCep.value).length === 8) consultar();
    });
  }

  function inicializarBlocosHorario() {
    var botaoAdicionar = document.getElementById("btn-adicionar-horario");
    var container = document.getElementById("horarios-blocos-container");
    var template = document.getElementById("horario-bloco-template");
    var totalForms = document.getElementById("id_horarios-TOTAL_FORMS");
    var maxForms = document.getElementById("id_horarios-MAX_NUM_FORMS");

    if (!botaoAdicionar || !container || !template || !totalForms) return;

    botaoAdicionar.addEventListener("click", function () {
      var indice = parseInt(totalForms.value, 10) || 0;
      var limite = parseInt((maxForms && maxForms.value) || "14", 10);
      if (indice >= limite) return;

      var html = template.innerHTML.replace(/__prefix__/g, String(indice));
      var wrapper = document.createElement("div");
      wrapper.innerHTML = html.trim();
      var novoBloco = wrapper.firstElementChild;
      if (!novoBloco) return;

      container.appendChild(novoBloco);
      totalForms.value = String(indice + 1);
      var primeiroInput = novoBloco.querySelector("input");
      if (primeiroInput) primeiroInput.focus();
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    inicializarMascaras();
    inicializarConsultaCep();
    inicializarBlocosHorario();
  });
})();
