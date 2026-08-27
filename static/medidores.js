(function () {
  const dashboard = document.getElementById('dashboard');

  function parseVoltage(value) {
    if (value == null || value === 'N/A' || value === '-') return NaN;
    const match = String(value).match(/-?\d+\.?\d*/);
    return match ? parseFloat(match[0]) : NaN;
  }

  function statusClass(item) {
    if (item.status !== 'online') return 'gray';
    const v = parseVoltage(item.summary?.tensao_a);
    if (Number.isNaN(v)) return 'gray';
    if (v < 190 || v > 250) return 'yellow';
    return 'green';
  }

  function statusLabel(item) {
    const labels = {
      online: 'Online',
      offline: 'Offline',
      timeout: 'Timeout',
      error: 'Erro',
    };
    return labels[item.status] || item.status;
  }

  function deviceLabel(type) {
    return type === 'ie_tecnologia' ? 'IE Tecnologia' : 'MiEnergy';
  }

  function renderCard(ip, item) {
    const card = document.createElement('div');
    card.className = `meter-card ${statusClass(item)}`;
    card.onclick = () => { window.location.href = `/medidores/${ip}`; };

    const s = item.summary || {};
    card.innerHTML = `
      <h3>${item.name || ip}</h3>
      <div class="ip">${ip}</div>
      <div class="metric">Tensão A: ${s.tensao_a || 'N/A'} V</div>
      <div class="metric">Potência: ${s.potencia_total || 'N/A'} W</div>
      <div class="metric">Consumo: ${s.energia_consumo || 'N/A'} kWh</div>
      <span class="badge">${deviceLabel(item.device_type)} · ${statusLabel(item)}</span>
    `;
    return card;
  }

  function render(data) {
    dashboard.innerHTML = '';
    const ips = Object.keys(data).sort();
    if (ips.length === 0) {
      dashboard.innerHTML = '<p class="loading">Nenhum medidor configurado.</p>';
      return;
    }
    ips.forEach(ip => dashboard.appendChild(renderCard(ip, data[ip])));
  }

  async function fetchData() {
    try {
      const response = await fetch('/medidores-data');
      const data = await response.json();
      render(data);
    } catch (err) {
      console.error(err);
      dashboard.innerHTML = '<p class="loading">Erro ao buscar medições.</p>';
    }
  }

  fetchData();
  setInterval(fetchData, 5000);
})();
