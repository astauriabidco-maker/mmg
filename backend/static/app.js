document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('date-display').textContent = new Date().toLocaleDateString();
    loadStats();
    // Auto-refresh every 60s
    setInterval(loadStats, 60000);
});

async function loadStats() {
    try {
        const response = await fetch('/stats/dashboard');
        const data = await response.json();

        // KPI Globaux
        document.getElementById('total-orders').textContent = data.total_orders;
        document.getElementById('total-time').textContent = (data.total_seconds / 3600).toFixed(1);

        // Tableau Postes
        const tbody = document.getElementById('stations-table-body');
        tbody.innerHTML = '';

        const labels = [];
        const values = [];

        data.stations.forEach(stat => {
            const row = document.createElement('tr');

            // Logic Alerte > 120%
            const ratio = stat.avg_duration / stat.standard;
            const isAlert = ratio > 1.2;
            const statusClass = isAlert ? 'status-warning' : 'status-ok';
            const statusText = isAlert ? 'ALERTE' : 'OK';

            row.innerHTML = `
                <td>${stat.name}</td>
                <td>${stat.count}</td>
                <td>${formatTime(stat.avg_duration)}</td>
                <td>${formatTime(stat.standard)}</td>
                <td>${(ratio * 100).toFixed(0)}%</td>
                <td><span class="${statusClass}">${statusText}</span></td>
            `;
            tbody.appendChild(row);

            labels.push(stat.name);
            values.push(stat.avg_duration);
        });

        updateChart(labels, values);

    } catch (error) {
        console.error("Erreur chargement stats:", error);
    }
}

function formatTime(seconds) {
    if (!seconds) return "-";
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}m ${s}s`;
}

let myChart = null;

function updateChart(labels, dataPoints) {
    const ctx = document.getElementById('timeChart').getContext('2d');

    if (myChart) {
        myChart.destroy();
    }

    myChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Temps Moyen (sec)',
                data: dataPoints,
                backgroundColor: 'rgba(52, 152, 219, 0.6)',
                borderColor: 'rgba(52, 152, 219, 1)',
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: { beginAtZero: true }
            }
        }
    });
}
