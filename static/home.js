(function () {
  const { useState, useEffect } = React;

  const Dashboard = () => {
    const [data, setData] = useState({});

    useEffect(() => {
      const fetchData = async () => {
        try {
          const response = await fetch('/dashboard-data');
          if (!response.ok) {
            throw new Error('Network response was not ok');
          }
          const result = await response.json();
          console.log('Data received:', result);
          setData(result);
        } catch (error) {
          console.error('Fetch error:', error);
          setData({ error: error.message });
        }
      };

      fetchData();
      const intervalId = setInterval(fetchData, 5000);
      return () => clearInterval(intervalId);
    }, []);

    const getStatusClass = (ip) => {
      const info = data[ip];
      if (!info) return 'gray';
      if (info.inputInfo.inputVoltage === 'N/A' || info.otherInfo.outputVoltage === 'N/A') return 'red';
      return 'green';
    };

    const handleClick = (ip) => {
      window.location.href = `/details/${ip}`;
    };

    return React.createElement(
      'div',
      { className: 'dashboard-grid' },
      Object.keys(data).length === 0
        ? React.createElement('p', { style: { textAlign: 'center', color: '#777', gridColumn: 'span 4' } }, 'Loading data...')
        : Object.keys(data).map(ip =>
            React.createElement(
              'div',
              {
                key: ip,
                className: `status-box ${getStatusClass(ip)}`,
                onClick: () => handleClick(ip),
              },
              React.createElement('span', {}, ip)
            )
          )
    );
  };

  ReactDOM.render(React.createElement(Dashboard), document.getElementById('dashboard'));
})();
