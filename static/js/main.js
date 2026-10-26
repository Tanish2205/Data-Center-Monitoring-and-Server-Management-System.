/*
main.js
-------
Handles the dashboard page: fetching live stats every few seconds,
updating the progress bars, and drawing the CPU/RAM chart.
*/

let historyChart = null;

function startDashboard() {
    loadSummary();
    loadLiveMetrics();
    loadHistory();

    // Refresh everything every 5 seconds
    setInterval(loadSummary, 5000);
    setInterval(loadLiveMetrics, 5000);
    setInterval(loadHistory, 5000);
}

async function loadSummary() {
    const res = await fetch('/api/dashboard/summary');
    const data = await res.json();

    if (document.getElementById('totalServers')) document.getElementById('totalServers').textContent = data.total_servers;
    if (document.getElementById('onlineServers')) document.getElementById('onlineServers').textContent = data.online_servers;
    if (document.getElementById('offlineServers')) document.getElementById('offlineServers').textContent = data.offline_servers;
    if (document.getElementById('totalUsers')) document.getElementById('totalUsers').textContent = data.total_users;
    if (document.getElementById('activeUsers')) document.getElementById('activeUsers').textContent = data.active_users;
    if (document.getElementById('offlineUsers')) document.getElementById('offlineUsers').textContent = data.offline_users;
    if (document.getElementById('activeAlerts')) document.getElementById('activeAlerts').textContent = data.active_alerts;
}

async function loadLiveMetrics() {
    const res = await fetch('/api/metrics/live');
    const data = await res.json();

    setBar('cpu', data.cpu_percent);
    setBar('ram', data.ram_percent);
    setBar('disk', data.disk_percent);

    document.getElementById('ramDetail').textContent =
        `${data.ram_used_mb} MB / ${data.ram_total_mb} MB`;
    document.getElementById('diskDetail').textContent =
        `${data.disk_used_gb} GB / ${data.disk_total_gb} GB`;
    document.getElementById('tempDetail').textContent =
        data.temperature ? `${data.temperature} °C` : 'not available';
    document.getElementById('netDetail').textContent =
        `${data.net_sent_mb} MB sent / ${data.net_recv_mb} MB received`;
}

function setBar(name, percent) {
    document.getElementById(name + 'Text').textContent = percent + '%';
    document.getElementById(name + 'Bar').style.width = percent + '%';
}

async function loadHistory() {
    const res = await fetch('/api/metrics/history');
    const data = await res.json();
    const noDataMsg = document.getElementById('noServerDataMsg');
    const chartCtx = document.getElementById('historyChart');

    if (!data || data.length === 0) {
        if (noDataMsg) noDataMsg.classList.remove('d-none');
        if (chartCtx) chartCtx.style.display = 'none';
        if (historyChart) {
            historyChart.data.labels = [];
            historyChart.data.datasets[0].data = [];
            historyChart.data.datasets[1].data = [];
            historyChart.update();
        }
        return;
    }

    if (noDataMsg) noDataMsg.classList.add('d-none');
    if (chartCtx) chartCtx.style.display = 'block';

    const labels = data.map(row => row.recorded_at.split(' ')[1] || '');
    const cpuValues = data.map(row => row.cpu_percent);
    const ramValues = data.map(row => row.ram_percent);

    if (!historyChart) {
        historyChart = new Chart(chartCtx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    { label: 'CPU %', data: cpuValues, borderColor: '#0d6efd', tension: 0.3 },
                    { label: 'RAM %', data: ramValues, borderColor: '#198754', tension: 0.3 }
                ]
            },
            options: {
                scales: { y: { min: 0, max: 100 } }
            }
        });
    } else {
        historyChart.data.labels = labels;
        historyChart.data.datasets[0].data = cpuValues;
        historyChart.data.datasets[1].data = ramValues;
        historyChart.update();
    }
}
