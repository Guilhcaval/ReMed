/* Consentimento explícito de geolocalização na busca (Spec 14 / RS010 / ADR 0006). */
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    const botaoGps = document.getElementById("btn-usar-localizacao");
    const statusGps = document.getElementById("status-geolocalizacao");
    const formGps = document.getElementById("form-localizacao-gps");
    const inputLat = document.getElementById("id_gps_latitude");
    const inputLon = document.getElementById("id_gps_longitude");

    if (!botaoGps || !formGps || !inputLat || !inputLon) {
      return;
    }

    function mostrarMensagem(texto) {
      if (statusGps) {
        statusGps.textContent = texto;
        statusGps.classList.remove("d-none");
      }
    }

    botaoGps.addEventListener("click", function () {
      if (!navigator.geolocation) {
        mostrarMensagem("Você pode informar seu CEP para ver os medicamentos mais próximos.");
        return;
      }

      botaoGps.disabled = true;
      mostrarMensagem("Obtendo sua localização aproximada...");

      navigator.geolocation.getCurrentPosition(
        function (posicao) {
          // Arredondamento imediato no cliente + servidor (~1,1 km — RS010).
          const lat = Number(posicao.coords.latitude).toFixed(2);
          const lon = Number(posicao.coords.longitude).toFixed(2);
          inputLat.value = lat;
          inputLon.value = lon;
          formGps.submit();
        },
        function () {
          botaoGps.disabled = false;
          mostrarMensagem("Você pode informar seu CEP para ver os medicamentos mais próximos.");
        },
        { enableHighAccuracy: false, timeout: 8000, maximumAge: 300000 }
      );
    });
  });
})();
