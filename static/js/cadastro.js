/* Melhoria progressiva para telas de cadastro e perfil do ReMed (ADR 0006 / ADR 0018).
 * Todo o fluxo permanece funcional sem JavaScript; validações reais ocorrem no servidor.
 */

(function () {
  "use strict";

  function somenteDigitos(valor) {
    return (valor || "").replace(/\D/g, "");
  }

  function aplicarMascaraCpf(valor) {
    var d = somenteDigitos(valor).slice(0, 11);
    if (d.length <= 3) return d;
    if (d.length <= 6) return d.slice(0, 3) + "." + d.slice(3);
    if (d.length <= 9) return d.slice(0, 3) + "." + d.slice(3, 6) + "." + d.slice(6);
    return d.slice(0, 3) + "." + d.slice(3, 6) + "." + d.slice(6, 9) + "-" + d.slice(9);
  }

  function aplicarMascaraCep(valor) {
    var d = somenteDigitos(valor).slice(0, 8);
    if (d.length <= 5) return d;
    return d.slice(0, 5) + "-" + d.slice(5);
  }

  function aplicarMascaraData(valor) {
    var d = somenteDigitos(valor).slice(0, 8);
    if (d.length <= 2) return d;
    if (d.length <= 4) return d.slice(0, 2) + "/" + d.slice(2);
    return d.slice(0, 2) + "/" + d.slice(2, 4) + "/" + d.slice(4);
  }

  function aplicarMascaraCelular(valor) {
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
        if (tipo === "cpf") {
          campo.value = aplicarMascaraCpf(campo.value);
        } else if (tipo === "cep") {
          campo.value = aplicarMascaraCep(campo.value);
        } else if (tipo === "data") {
          campo.value = aplicarMascaraData(campo.value);
        } else if (tipo === "celular") {
          campo.value = aplicarMascaraCelular(campo.value);
        }
      });
    });
  }

  function inicializarToggleSenha() {
    var botoes = document.querySelectorAll("[data-toggle-senha]");
    botoes.forEach(function (botao) {
      var alvoId = botao.getAttribute("data-toggle-senha");
      var campoSenha = document.getElementById(alvoId);
      if (!campoSenha) return;

      botao.addEventListener("click", function () {
        var visivel = campoSenha.type === "text";
        campoSenha.type = visivel ? "password" : "text";
        botao.textContent = visivel ? "Mostrar" : "Ocultar";
        botao.setAttribute("aria-pressed", visivel ? "false" : "true");
        botao.setAttribute(
          "aria-label",
          visivel ? "Mostrar senha" : "Ocultar senha"
        );
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
    var ultimoCepConsultado = "";

    function definirStatus(texto, tipo) {
      if (!statusEl) return;
      statusEl.textContent = texto;
      statusEl.className = "remed-hint mt-1";
      if (tipo === "erro") {
        statusEl.classList.add("text-danger");
      } else if (tipo === "sucesso") {
        statusEl.classList.add("text-success");
      }
    }

    function consultarCep() {
      var digitos = somenteDigitos(campoCep.value);
      if (digitos.length !== 8 || digitos === ultimoCepConsultado) {
        return;
      }
      ultimoCepConsultado = digitos;
      definirStatus("Buscando endereço pelo CEP...", "info");

      var url = urlBase.replace("00000000", digitos);
      fetch(url, {
        method: "GET",
        headers: { Accept: "application/json" },
        credentials: "same-origin",
      })
        .then(function (resposta) {
          return resposta.json().then(function (dados) {
            return { ok: resposta.ok, dados: dados };
          });
        })
        .then(function (resultado) {
          if (!resultado.ok) {
            var aviso =
              (resultado.dados && resultado.dados.erro) ||
              "Não foi possível consultar o CEP. Preencha o endereço manualmente.";
            definirStatus(aviso, "erro");
            return;
          }
          var d = resultado.dados;
          if (campoLogradouro && d.logradouro) campoLogradouro.value = d.logradouro;
          if (campoBairro && d.bairro) campoBairro.value = d.bairro;
          if (campoMunicipio && d.municipio) campoMunicipio.value = d.municipio;
          if (campoEstado && d.estado) campoEstado.value = d.estado;
          definirStatus(
            "Endereço preenchido pelo CEP. Confira os dados e informe o número.",
            "sucesso"
          );
          if (campoNumero && !campoNumero.value) {
            campoNumero.focus();
          }
        })
        .catch(function () {
          definirStatus(
            "Consulta de CEP indisponível no momento. Preencha o endereço manualmente.",
            "erro"
          );
        });
    }

    campoCep.addEventListener("blur", consultarCep);
    campoCep.addEventListener("input", function () {
      var digitos = somenteDigitos(campoCep.value);
      if (digitos.length === 8) {
        consultarCep();
      }
    });
  }

  function inicializarCopiaChave() {
    var botoes = document.querySelectorAll("[data-copiar-alvo]");
    var status = document.getElementById("totp-copia-status");
    botoes.forEach(function (botao) {
      var alvo = document.getElementById(botao.getAttribute("data-copiar-alvo"));
      if (!alvo) return;
      botao.addEventListener("click", function () {
        var texto = (alvo.textContent || "").trim();
        if (!texto || !navigator.clipboard) return;
        navigator.clipboard.writeText(texto).then(function () {
          if (status) status.textContent = "Chave manual copiada para a área de transferência.";
        });
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    inicializarMascaras();
    inicializarToggleSenha();
    inicializarConsultaCep();
    inicializarCopiaChave();
  });
})();
