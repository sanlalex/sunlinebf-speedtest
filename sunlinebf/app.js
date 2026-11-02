(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const fields = { technician: $('technician'), site: $('site') };
  const button = $('startButton');
  const copyButton = $('copyButton');
  const phase = $('phase');
  const error = $('error');
  const historyStatus = $('historyStatus');
  const historyRows = $('historyRows');
  const retrySaveButton = $('retrySaveButton');
  const previousPageButton = $('previousPage');
  const nextPageButton = $('nextPage');
  const pageLabel = $('pageLabel');
  const historyApi = new URL('/api/results', window.location.origin).toString();
  const speedtestUrl = new URL(window.location.href);
  speedtestUrl.port = '8080';
  speedtestUrl.pathname = '/';
  speedtestUrl.search = '';
  speedtestUrl.hash = '';
  let test;
  let latest = null;
  let startedAt = null;
  let finishedAt = null;
  let pendingSave = null;
  let searchTimer = null;
  let historyRequestId = 0;
  const historyPageSize = 50;
  let historyOffset = 0;
  let historyTotal = 0;

  const server = {
    name: 'Serveur SunlineBF',
    server: speedtestUrl.origin + '/',
    dlURL: 'backend/garbage',
    ulURL: 'backend/empty',
    pingURL: 'backend/empty',
    getIpURL: 'backend/getIP'
  };

  function setMetric(id, value, decimals = 1) {
    if (value == null || String(value).trim() === '') {
      $(id).textContent = '—';
      return;
    }
    const number = Number(value);
    $(id).textContent = Number.isFinite(number) && number >= 0 ? number.toFixed(decimals) : '—';
  }

  function update(data) {
    latest = data;
    const state = Number(data.testState);
    setMetric('download', data.dlStatus, Number(data.dlStatus) < 10 ? 2 : 1);
    setMetric('upload', data.ulStatus, Number(data.ulStatus) < 10 ? 2 : 1);
    setMetric('ping', data.pingStatus, 1);
    setMetric('jitter', data.jitterStatus, 1);
    const progress = Math.max(0, Math.min(1, Number(data.dlProgress || 0) * 0.45 + Number(data.pingProgress || 0) * 0.1 + Number(data.ulProgress || 0) * 0.45));
    $('progress').style.width = `${Math.round(progress * 100)}%`;
    phase.textContent = ({ 0: 'Démarrage…', 1: 'Mesure du téléchargement', 2: 'Mesure de la latence', 3: 'Mesure de l’envoi', 4: 'Test terminé', 5: 'Test interrompu' })[state] || 'Mesure en cours';
    if (data.clientIp) $('clientIp').textContent = data.clientIp;
  }

  function setRunning(running) {
    button.classList.toggle('running', running);
    $('buttonLabel').textContent = running ? 'Arrêter le test' : 'Relancer le test';
    button.querySelector('[aria-hidden="true"]').textContent = running ? '■' : '▶';
  }

  function finish(aborted) {
    setRunning(false);
    button.disabled = false;
    if (aborted) {
      phase.textContent = 'Test interrompu';
      $('testNote').textContent = 'Mesure arrêtée. Vous pouvez relancer un test.';
      return;
    }
    finishedAt = new Date();
    $('progress').style.width = '100%';
    $('report').hidden = false;
    $('testNote').textContent = 'Mesure terminée. Copiez le rapport pour le transmettre à votre équipe.';
    const rawMetrics = [latest && latest.dlStatus, latest && latest.ulStatus, latest && latest.pingStatus, latest && latest.jitterStatus];
    if (rawMetrics.some((value) => value == null || String(value).trim() === '')) {
      historyStatus.textContent = 'Test terminé, mais les mesures sont incomplètes et ne peuvent pas être enregistrées.';
      return;
    }
    const metrics = rawMetrics.map(Number);
    if (metrics.some((value) => !Number.isFinite(value) || value < 0)) {
      historyStatus.textContent = 'Test terminé, mais une mesure est invalide et ne peut pas être enregistrée.';
      return;
    }
    const candidate = {
      request_id: makeRequestId(),
      technician: fields.technician.value.trim(),
      site: fields.site.value.trim(),
      download: metrics[0],
      upload: metrics[1],
      ping: metrics[2],
      jitter: metrics[3]
    };
    pendingSave = candidate;
    saveResult();
  }

  function makeRequestId() {
    if (window.crypto && typeof window.crypto.randomUUID === 'function') return window.crypto.randomUUID();
    if (window.crypto && typeof window.crypto.getRandomValues === 'function') {
      const bytes = new Uint8Array(16);
      window.crypto.getRandomValues(bytes);
      bytes[6] = (bytes[6] & 0x0f) | 0x40;
      bytes[8] = (bytes[8] & 0x3f) | 0x80;
      const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('');
      return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
    }
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (character) => {
      const random = Math.floor(Math.random() * 16);
      return (character === 'x' ? random : (random & 0x3) | 0x8).toString(16);
    });
  }

  async function saveResult() {
    if (!pendingSave) return;
    retrySaveButton.hidden = true;
    historyStatus.textContent = 'Enregistrement du résultat…';
    try {
      const response = await fetch(historyApi, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(pendingSave)
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      pendingSave = null;
      historyStatus.textContent = 'Résultat enregistré dans l’historique partagé.';
      historyOffset = 0;
      await loadHistory($('historySearch').value.trim());
    } catch (e) {
      historyStatus.textContent = 'Le test est terminé, mais le résultat n’a pas pu être enregistré. Vérifiez la connexion au serveur puis réessayez.';
      retrySaveButton.hidden = false;
    }
  }

  function formatDate(value) {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? 'Date inconnue' : date.toLocaleString('fr-FR');
  }

  function metricCell(value, suffix, digits = 1) {
    const number = Number(value);
    return Number.isFinite(number) && number >= 0 ? `${number.toFixed(digits)} ${suffix}` : '—';
  }

  function renderHistory(items) {
    historyRows.replaceChildren();
    if (!Array.isArray(items) || items.length === 0) {
      const row = document.createElement('tr');
      const cell = document.createElement('td');
      cell.colSpan = 7;
      cell.textContent = 'Aucun résultat trouvé.';
      row.appendChild(cell);
      historyRows.appendChild(row);
      return;
    }
    for (const item of items) {
      const row = document.createElement('tr');
      const values = [
        formatDate(item.created_at), item.technician || '—', item.site || '—',
        metricCell(item.download, 'Mbit/s'), metricCell(item.upload, 'Mbit/s'),
        metricCell(item.ping, 'ms'), metricCell(item.jitter, 'ms')
      ];
      for (const value of values) {
        const cell = document.createElement('td');
        cell.textContent = value;
        row.appendChild(cell);
      }
      historyRows.appendChild(row);
    }
  }

  async function loadHistory(search = $('historySearch').value.trim()) {
    const requestId = ++historyRequestId;
    historyStatus.textContent = 'Chargement de l’historique…';
    try {
      const url = new URL(historyApi);
      url.searchParams.set('limit', String(historyPageSize));
      url.searchParams.set('offset', String(historyOffset));
      if (search) url.searchParams.set('search', search);
      const response = await fetch(url);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      if (requestId !== historyRequestId) return;
      renderHistory(data.items);
      historyTotal = Number(data.total) || 0;
      const currentPage = Math.floor(historyOffset / historyPageSize) + 1;
      const lastPage = Math.max(1, Math.ceil(historyTotal / historyPageSize));
      pageLabel.textContent = `Page ${currentPage} sur ${lastPage}`;
      previousPageButton.disabled = historyOffset === 0;
      nextPageButton.disabled = historyOffset + historyPageSize >= historyTotal;
      historyStatus.textContent = `${historyTotal} résultat(s) dans l’historique partagé.`;
    } catch (_) {
      if (requestId !== historyRequestId) return;
      historyStatus.textContent = 'Historique indisponible. Vérifiez que le service d’historique est démarré.';
    }
  }

  function testFailure(reason) {
    error.hidden = false;
    error.textContent = `Le test n’a pas pu démarrer. Vérifiez l’accès au serveur SunlineBF puis réessayez. ${reason ? `Détail : ${reason}` : ''}`;
    phase.textContent = 'Serveur inaccessible';
    $('connectionDot').className = 'status-dot offline';
    $('connectionLabel').textContent = 'Serveur inaccessible';
    button.disabled = true;
    $('buttonLabel').textContent = 'Serveur indisponible';
  }

  function startStop() {
    if (!test) return;
    error.hidden = true;
    if (test.getState() === 3) {
      test.abort();
      return;
    }
    if (pendingSave) {
      historyStatus.textContent = 'Enregistrez ou réessayez le dernier résultat avant de lancer un nouveau test.';
      retrySaveButton.hidden = false;
      return;
    }
    startedAt = new Date();
    finishedAt = null;
    $('report').hidden = true;
    $('testNote').textContent = 'Mesure en cours. Gardez cette page ouverte jusqu’à la fin.';
    setRunning(true);
    button.disabled = false;
    test.onupdate = update;
    test.onend = finish;
    try {
      test.start();
    } catch (e) {
      testFailure(e && e.message ? e.message : '');
    }
  }

  function reportText() {
    const lines = [
      'SUNLINEBF — RAPPORT DE TEST RÉSEAU',
      `Date : ${(finishedAt || new Date()).toLocaleString('fr-FR')}`,
      `Site / client : ${fields.site.value.trim() || 'Non renseigné'}`,
      `Technicien : ${fields.technician.value.trim() || 'Non renseigné'}`,
      `Téléchargement : ${$('download').textContent} Mbit/s`,
      `Envoi : ${$('upload').textContent} Mbit/s`,
      `Latence : ${$('ping').textContent} ms`,
      `Gigue : ${$('jitter').textContent} ms`,
      `Adresse IP détectée : ${latest && latest.clientIp ? latest.clientIp : 'Non disponible'}`,
      `Serveur : ${server.name}`,
      `Durée : ${startedAt && finishedAt ? Math.max(1, Math.round((finishedAt - startedAt) / 1000)) + ' s' : 'Non disponible'}`
    ];
    return lines.join('\n');
  }

  async function copyReport() {
    try {
      await navigator.clipboard.writeText(reportText());
      copyButton.textContent = 'Rapport copié';
      window.setTimeout(() => { copyButton.textContent = 'Copier le rapport'; }, 2200);
    } catch (_) {
      const area = document.createElement('textarea');
      area.value = reportText();
      area.setAttribute('readonly', '');
      area.style.position = 'fixed';
      area.style.opacity = '0';
      document.body.appendChild(area);
      try {
        area.select();
        if (!document.execCommand('copy')) throw new Error('Copy command was rejected');
        copyButton.textContent = 'Rapport copié';
        window.setTimeout(() => { copyButton.textContent = 'Copier le rapport'; }, 2200);
      } catch (_) {
        error.hidden = false;
        error.textContent = 'Impossible de copier le rapport dans le presse-papiers. Vérifiez les autorisations du navigateur et réessayez.';
      } finally {
        area.remove();
      }
    }
  }

  function initialize() {
    if (typeof Speedtest !== 'function') {
      testFailure('Le moteur de test LibreSpeed ne s’est pas chargé.');
      return;
    }
    test = new Speedtest();
    test.setParameter('telemetry_level', 0);
    test.addTestPoint(server);
    test.selectServer((selected) => {
      if (!selected) {
        testFailure('Aucun serveur de mesure n’a répondu.');
        return;
      }
      test.setSelectedServer(selected);
      $('connectionDot').className = 'status-dot online';
      $('connectionLabel').textContent = 'Serveur prêt';
      phase.textContent = 'Prêt à mesurer';
      $('testNote').textContent = 'Les tests terminés sont enregistrés sur le serveur et partagés avec l’équipe.';
      $('buttonLabel').textContent = 'Lancer le test';
      button.disabled = false;
    });
  }

  button.addEventListener('click', startStop);
  copyButton.addEventListener('click', copyReport);
  $('refreshHistory').addEventListener('click', () => loadHistory($('historySearch').value.trim()));
  previousPageButton.addEventListener('click', () => {
    historyOffset = Math.max(0, historyOffset - historyPageSize);
    loadHistory();
  });
  nextPageButton.addEventListener('click', () => {
    if (historyOffset + historyPageSize >= historyTotal) return;
    historyOffset += historyPageSize;
    loadHistory();
  });
  retrySaveButton.addEventListener('click', saveResult);
  $('historySearch').addEventListener('input', () => {
    window.clearTimeout(searchTimer);
    historyRequestId += 1;
    searchTimer = window.setTimeout(() => {
      historyOffset = 0;
      loadHistory($('historySearch').value.trim());
    }, 250);
  });
  loadHistory();
  initialize();
})();

