/* Melhoria progressiva do formulário de doação (Specs 08, 09 e 23 / ADR 0006 / ADR 0021). */
(function () {
  "use strict";

  const CAMPOS_IA = [
    { chave: "nome_medicamento", inputId: "id_nome_medicamento", badgeId: "badge-ia-nome_medicamento" },
    { chave: "principio_ativo", inputId: "id_principio_ativo", badgeId: "badge-ia-principio_ativo" },
    { chave: "concentracao_dosagem", inputId: "id_concentracao_dosagem", badgeId: "badge-ia-concentracao_dosagem" },
    { chave: "fabricante", inputId: "id_fabricante", badgeId: "badge-ia-fabricante" },
    { chave: "lote", inputId: "id_lote", badgeId: "badge-ia-lote" },
    { chave: "data_validade", inputId: "id_data_validade", badgeId: "badge-ia-data_validade" },
  ];

  function obterCsrfToken(form) {
    const inputCsrf = form ? form.querySelector('input[name="csrfmiddlewaretoken"]') : null;
    return inputCsrf ? inputCsrf.value : "";
  }

  function limparBadgesIa() {
    CAMPOS_IA.forEach(function (cfg) {
      const input = document.getElementById(cfg.inputId);
      const badgeBox = document.getElementById(cfg.badgeId);
      if (input) {
        input.classList.remove("remed-campo-ia-sugerido", "remed-campo-ia-baixa");
      }
      if (badgeBox) {
        badgeBox.textContent = "";
        badgeBox.classList.add("d-none");
      }
    });
  }

  function renderizarBadgeCampo(badgeBox, campoDados, ehValidade) {
    if (!badgeBox || !campoDados || !campoDados.valor) {
      return;
    }
    badgeBox.textContent = "";
    badgeBox.classList.remove("d-none");

    const seloSugestao = document.createElement("span");
    seloSugestao.className = "badge rounded-pill remed-badge-ia-sugestao me-1";
    seloSugestao.textContent = "Sugestão da IA";
    badgeBox.appendChild(seloSugestao);

    if (campoDados.baixa_confianca) {
      const seloBaixa = document.createElement("span");
      seloBaixa.className = "badge rounded-pill remed-badge-ia-baixa me-1";
      seloBaixa.textContent = "Baixa confiança — revise manualmente";
      badgeBox.appendChild(seloBaixa);
    }

    if (ehValidade) {
      const seloValidade = document.createElement("span");
      seloValidade.className = "badge rounded-pill remed-badge-ia-baixa";
      seloValidade.textContent = "Confirme a validade na embalagem";
      badgeBox.appendChild(seloValidade);
    }
  }

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

    // --- Leitura da embalagem por IA (RF009 / Spec 23 / ADR 0021) ---
    const painelIa = document.getElementById("painel-leitura-ia");
    if (!painelIa) {
      return;
    }

    const formDoacao = painelIa.closest("form");
    const inputFoto1 = document.getElementById("id_foto_1");
    const checkConsentimento = document.getElementById("id_consentimento_ia");
    const botaoLerIa = document.getElementById("btn-ler-embalagem-ia");
    const statusIa = document.getElementById("ia-status-mensagem");
    const blocoConfirmacoesIa = document.getElementById("bloco-confirmacoes-ia");
    const grupoConfirmarValidade = document.getElementById("grupo-confirmar-validade-ia");
    const grupoConfirmarBaixa = document.getElementById("grupo-confirmar-baixa-ia");
    const hiddenUsouIa = document.getElementById("id_ia_sugestao_utilizada");
    const hiddenValidadeIa = document.getElementById("id_ia_validade_sugerida");
    const hiddenBaixaIa = document.getElementById("id_ia_campos_baixa_confianca");
    const checkConfirmaValidade = document.getElementById("id_confirmar_validade_ia");
    const checkConfirmaBaixa = document.getElementById("id_confirmar_baixa_confianca_ia");
    const urlEndpointIa = painelIa.getAttribute("data-url-ia") || "";

    function exibirMensagemIa(texto, tipoClasse) {
      if (!statusIa) {
        return;
      }
      statusIa.className = "alert small py-2 mt-3 mb-0 " + tipoClasse;
      statusIa.textContent = texto;
      statusIa.classList.remove("d-none");
    }

    function atualizarEstadoBotaoIa() {
      if (!botaoLerIa) {
        return;
      }
      const temFoto = Boolean(inputFoto1 && inputFoto1.files && inputFoto1.files.length > 0);
      const consentiu = Boolean(checkConsentimento && checkConsentimento.checked);
      botaoLerIa.disabled = !(temFoto && consentiu);
    }

    function sincronizarBlocosConfirmacao() {
      if (!blocoConfirmacoesIa) {
        return;
      }
      const precisaValidade = Boolean(hiddenValidadeIa && hiddenValidadeIa.value === "sim");
      const precisaBaixa = Boolean(hiddenBaixaIa && hiddenBaixaIa.value.trim() !== "");
      if (grupoConfirmarValidade) {
        grupoConfirmarValidade.classList.toggle("d-none", !precisaValidade);
      }
      if (grupoConfirmarBaixa) {
        grupoConfirmarBaixa.classList.toggle("d-none", !precisaBaixa);
      }
      blocoConfirmacoesIa.classList.toggle("d-none", !(precisaValidade || precisaBaixa));
    }

    if (inputFoto1) {
      inputFoto1.addEventListener("change", atualizarEstadoBotaoIa);
    }
    if (checkConsentimento) {
      checkConsentimento.addEventListener("change", atualizarEstadoBotaoIa);
    }
    atualizarEstadoBotaoIa();
    sincronizarBlocosConfirmacao();

    if (botaoLerIa && urlEndpointIa) {
      botaoLerIa.addEventListener("click", function () {
        if (!inputFoto1 || !inputFoto1.files || inputFoto1.files.length === 0) {
          exibirMensagemIa(
            "Selecione primeiro a Foto 1 da embalagem (JPG ou PNG) para ler os dados com IA.",
            "alert-warning"
          );
          return;
        }
        if (!checkConsentimento || !checkConsentimento.checked) {
          exibirMensagemIa(
            "Marque a confirmação de ciência sobre o envio da foto ao serviço externo de IA.",
            "alert-warning"
          );
          return;
        }

        const textoOriginal = botaoLerIa.textContent;
        botaoLerIa.disabled = true;
        botaoLerIa.textContent = "Lendo embalagem...";
        exibirMensagemIa(
          "Analisando a foto da embalagem (até 15 segundos). Você pode aguardar ou preencher manualmente.",
          "alert-info"
        );

        const dadosEnvio = new FormData();
        dadosEnvio.append("foto", inputFoto1.files[0]);
        dadosEnvio.append("consentimento_ia", "sim");

        fetch(urlEndpointIa, {
          method: "POST",
          body: dadosEnvio,
          credentials: "same-origin",
          headers: {
            "X-CSRFToken": obterCsrfToken(formDoacao),
            Accept: "application/json",
          },
        })
          .then(function (resp) {
            return resp
              .json()
              .catch(function () {
                return {
                  erro:
                    "Não foi possível ler a embalagem automaticamente no momento. " +
                    "Preencha os campos manualmente — nada do que você digitou foi perdido.",
                };
              })
              .then(function (json) {
                return { ok: resp.ok, status: resp.status, json: json };
              });
          })
          .then(function (res) {
            if (!res.ok || !res.json || !res.json.sucesso) {
              const msgErro =
                (res.json && res.json.erro) ||
                "Não foi possível ler a embalagem automaticamente no momento. " +
                  "Preencha os campos manualmente — nada do que você digitou foi perdido.";
              exibirMensagemIa(msgErro, "alert-warning");
              return;
            }

            limparBadgesIa();
            const campos = res.json.campos || {};
            let preenchidos = 0;

            CAMPOS_IA.forEach(function (cfg) {
              const sugestao = campos[cfg.chave];
              const input = document.getElementById(cfg.inputId);
              const badgeBox = document.getElementById(cfg.badgeId);
              if (!sugestao || !sugestao.valor || !input) {
                return;
              }
              input.value = sugestao.valor;
              preenchidos += 1;
              if (sugestao.baixa_confianca || cfg.chave === "data_validade") {
                input.classList.add("remed-campo-ia-baixa");
              } else {
                input.classList.add("remed-campo-ia-sugerido");
              }
              renderizarBadgeCampo(badgeBox, sugestao, cfg.chave === "data_validade");
            });

            if (hiddenUsouIa) {
              hiddenUsouIa.value = preenchidos > 0 ? "sim" : "nao";
            }
            if (hiddenValidadeIa) {
              hiddenValidadeIa.value = res.json.validade_sugerida ? "sim" : "nao";
            }
            if (hiddenBaixaIa) {
              const listaBaixa = Array.isArray(res.json.campos_baixa_confianca)
                ? res.json.campos_baixa_confianca
                : [];
              hiddenBaixaIa.value = listaBaixa.join(",");
            }
            if (checkConfirmaValidade) {
              checkConfirmaValidade.checked = false;
            }
            if (checkConfirmaBaixa) {
              checkConfirmaBaixa.checked = false;
            }
            sincronizarBlocosConfirmacao();

            if (preenchidos > 0) {
              exibirMensagemIa(
                res.json.aviso_sugestao ||
                  "Sugestão da IA — confira os dados e confirme especialmente a data de validade.",
                "alert-success"
              );
            } else {
              exibirMensagemIa(
                "A IA não conseguiu identificar campos legíveis nesta imagem. Preencha os dados manualmente.",
                "alert-warning"
              );
            }
          })
          .catch(function () {
            exibirMensagemIa(
              "Não foi possível ler a embalagem automaticamente no momento. " +
                "Preencha os campos manualmente — nada do que você digitou foi perdido.",
              "alert-warning"
            );
          })
          .finally(function () {
            botaoLerIa.textContent = textoOriginal;
            atualizarEstadoBotaoIa();
          });
      });
    }
  });
})();
