(function () {
  const { useState, useEffect } = React;

  const Dashboard = () => {
    const [data, setData] = useState({});

    useEffect(() => {
      const fetchData = async () => {
        try {
          const response = await fetch('/dashboard-data');
          const result = await response.json();
          setData(result);
        } catch (error) {
          console.error('Erro ao buscar dados:', error);
        }
      };

      fetchData();
      const intervalId = setInterval(fetchData, 5000);
      return () => clearInterval(intervalId);
    }, []);

    const getStatusClass = (ip) => {
      const info = data[ip];
      if (!info) return 'gray';

      let batteryPercentage = 100;
      const batteryStr = info.otherInfo?.percentualCarga || '100 %';
      const batteryMatch = batteryStr.match(/(\d+)/);
      if (batteryMatch) {
        batteryPercentage = parseInt(batteryMatch[1]);
      }

      const inputVoltageStr = info.inputInfo?.inputVoltage || '0';
      const voltageMatch = inputVoltageStr.match(/(\d+\.?\d*)/);
      const inputVoltage = voltageMatch ? parseFloat(voltageMatch[1]) : NaN;

      if (Number.isNaN(inputVoltage)) return 'gray';
      if (batteryPercentage < 50) return 'red';
      if (inputVoltage < 200) return 'yellow';
      if (batteryPercentage < 100) return 'yellow';
      return 'green';
    };

    const handleClick = (ip) => {
      window.location.href = `/details/${ip}`;
    };

    return React.createElement(
      'div',
      { className: 'dashboard-grid' },
      Object.keys(data).length === 0
        ? React.createElement('p', { style: { textAlign: 'center', color: '#777', gridColumn: 'span 8' } }, 'Loading data...')
        : Object.keys(data).map(ip => {
            const info = data[ip];
            const batteryLevel = info?.otherInfo?.percentualCarga || '100 %';
            const inputVoltage = info?.inputInfo?.inputVoltage || 'N/A';

            return React.createElement(
              'div',
              {
                key: ip,
                className: `status-box ${getStatusClass(ip)}`,
                onClick: () => handleClick(ip),
              },
              React.createElement('span', {
                style: {
                  position: 'absolute',
                  top: '50%',
                  left: '50%',
                  transform: 'translate(-50%, -50%)',
                  textAlign: 'center',
                  color: 'white',
                  fontWeight: 'bold',
                  width: '130px'
                }
              },
                React.createElement('div', { style: { fontSize: '11px', marginBottom: '5px' } }, ip),
                React.createElement('div', { style: { fontSize: '9px', marginTop: '2px' } },
                  `Bateria: ${batteryLevel}`
                ),
                React.createElement('div', { style: { fontSize: '9px', marginTop: '2px' } },
                  `Entrada: ${inputVoltage}`
                )
              )
            );
          })
    );
  };

  const ConfigModal = ({ onClose }) => {
    const [rows, setRows] = useState([]);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [message, setMessage] = useState('');
    const [error, setError] = useState(false);

    useEffect(() => {
      fetch('/api/nobreak-config')
        .then(r => r.json())
        .then(list => {
          setRows(Array.isArray(list) ? list : []);
          setLoading(false);
        })
        .catch(err => {
          setMessage('Falha ao carregar configs: ' + err.message);
          setError(true);
          setLoading(false);
        });
    }, []);

    const updateRow = (ip, field, value) => {
      setRows(prev => prev.map(r => (r.ip === ip ? { ...r, [field]: value } : r)));
    };

    const handleSave = async () => {
      setSaving(true);
      setMessage('');
      setError(false);
      try {
        for (const row of rows) {
          const res = await fetch(`/api/nobreak-config/${encodeURIComponent(row.ip)}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              protocol: row.protocol,
              auth_required: !!row.auth_required,
            }),
          });
          if (!res.ok) {
            const body = await res.json().catch(() => ({}));
            throw new Error(body.error || `Erro ao salvar ${row.ip}`);
          }
        }
        setMessage('Configurações salvas. O próximo refresh do painel já usa o novo protocolo.');
      } catch (err) {
        setError(true);
        setMessage(err.message || 'Erro ao salvar');
      } finally {
        setSaving(false);
      }
    };

    return ReactDOM.createPortal(
      React.createElement(
        'div',
        {
          className: 'modal-overlay',
          onClick: (e) => { if (e.target === e.currentTarget) onClose(); },
        },
        React.createElement(
          'div',
          { className: 'modal' },
          React.createElement('h2', null, 'Configuração por nobreak'),
          React.createElement(
            'p',
            { className: 'hint' },
            'Use quando trocar o equipamento: "Antigo (HTML)" = ups.cgi / ddata.html; "Novo (JSON)" = get_dashboard.cgi. Marque autenticação se o aparelho pedir login.'
          ),
          loading
            ? React.createElement('p', null, 'Carregando...')
            : React.createElement(
                'table',
                { className: 'config-table' },
                React.createElement(
                  'thead',
                  null,
                  React.createElement(
                    'tr',
                    null,
                    React.createElement('th', null, 'Nobreak'),
                    React.createElement('th', null, 'IP'),
                    React.createElement('th', null, 'Protocolo'),
                    React.createElement('th', null, 'Auth')
                  )
                ),
                React.createElement(
                  'tbody',
                  null,
                  rows.map(row =>
                    React.createElement(
                      'tr',
                      { key: row.ip },
                      React.createElement('td', null, row.name),
                      React.createElement('td', null, row.ip),
                      React.createElement(
                        'td',
                        null,
                        React.createElement(
                          'select',
                          {
                            value: row.protocol || 'legacy',
                            onChange: (e) => updateRow(row.ip, 'protocol', e.target.value),
                          },
                          React.createElement('option', { value: 'legacy' }, 'Antigo (HTML)'),
                          React.createElement('option', { value: 'special' }, 'Novo (JSON)')
                        )
                      ),
                      React.createElement(
                        'td',
                        null,
                        React.createElement('input', {
                          type: 'checkbox',
                          checked: !!row.auth_required,
                          onChange: (e) => updateRow(row.ip, 'auth_required', e.target.checked),
                        })
                      )
                    )
                  )
                )
              ),
          message
            ? React.createElement('div', { className: 'save-msg' + (error ? ' error' : '') }, message)
            : null,
          React.createElement(
            'div',
            { className: 'modal-actions' },
            React.createElement('button', { className: 'btn-cancel', onClick: onClose, type: 'button' }, 'Fechar'),
            React.createElement(
              'button',
              {
                className: 'btn-save',
                onClick: handleSave,
                type: 'button',
                disabled: saving || loading,
              },
              saving ? 'Salvando...' : 'Salvar'
            )
          )
        )
      ),
      document.body
    );
  };

  const App = () => {
    const [showConfig, setShowConfig] = useState(false);

    useEffect(() => {
      const btn = document.getElementById('open-config');
      if (!btn) return undefined;
      const open = () => setShowConfig(true);
      btn.addEventListener('click', open);
      return () => btn.removeEventListener('click', open);
    }, []);

    return React.createElement(
      React.Fragment,
      null,
      React.createElement(Dashboard),
      showConfig ? React.createElement(ConfigModal, { onClose: () => setShowConfig(false) }) : null
    );
  };

  ReactDOM.render(React.createElement(App), document.getElementById('dashboard'));
})();
