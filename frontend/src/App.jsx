import { useState, useEffect } from 'react'
import axios from 'axios'

// Components
const KPICard = ({ label, value, unit = "" }) => (
    <div className="kpi-card">
        <div className="kpi-value">{value}{unit}</div>
        <div className="kpi-label">{label}</div>
    </div>
)

const StationTable = ({ title, data }) => (
    <div className="section-card">
        <h2 className="section-title">{title}</h2>
        <table>
            <thead>
                <tr>
                    <th>Poste</th>
                    <th>Moyenne (s)</th>
                </tr>
            </thead>
            <tbody>
                {data.length === 0 ? (
                    <tr><td colSpan="2">Pas de données</td></tr>
                ) : (
                    data.map((row, idx) => (
                        <tr key={idx}>
                            <td>{row.station}</td>
                            <td>{row.avg_seconds}</td>
                        </tr>
                    ))
                )}
            </tbody>
        </table>
    </div>
)

const AlertList = ({ alerts }) => (
    <div className="section-card full-width" style={{ marginTop: '20px' }}>
        <h2 className="section-title" style={{ color: '#c0392b' }}>ALERTES ({alerts.length})</h2>
        {alerts.length === 0 ? (
            <p>Aucune alerte en cours.</p>
        ) : (
            alerts.map((alert, idx) => (
                <div key={idx} className="alert-item">
                    <strong>{alert.order}</strong>
                    <span>{alert.station}</span>
                    <span>{alert.duration}s (Max: {alert.limit}s)</span>
                </div>
            ))
        )}
    </div>
)

function App() {
    const [metrics, setMetrics] = useState(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(null)

    const fetchData = async () => {
        try {
            // In Dev: Vite proxies or CORS. 
            // In Prod (FastAPI static): relative path works.
            // Assuming Vite proxy configured or CORS enabled on Backend if dev.
            // For V1 simple: direct call, expect CORS or proxy.
            // Let's assume production relative URL for build.
            // For Dev, might fail without proxy. 
            // Setting full URL for dev safety if needed, but relative best for deployment.
            const res = await axios.get('/dashboard/metrics')
            setMetrics(res.data)
            setError(null)
        } catch (err) {
            console.error(err)
            setError("Erreur chargement données")
        } finally {
            setLoading(false)
        }
    }

    useEffect(() => {
        fetchData()
        const interval = setInterval(fetchData, 15000)
        return () => clearInterval(interval)
    }, [])

    if (loading) return <div className="dashboard-container">Chargement...</div>
    if (error) return <div className="dashboard-container" style={{ color: 'red' }}>{error}</div>
    if (!metrics) return null

    return (
        <div className="dashboard-container">
            <header className="header">
                <h1>Atelier Menuiserie - Suivi V1</h1>
                <span>Actualisé: {new Date().toLocaleTimeString()}</span>
            </header>

            <div className="kpi-grid">
                <KPICard label="Commandes En Cours" value={metrics.kpi.active_orders} />
                <KPICard label="Temps Moyen Global" value={metrics.kpi.global_avg_seconds} unit="s" />
                <KPICard label="Alertes (>120%)" value={metrics.kpi.alerts_percent} unit="%" />
            </div>

            <div className="content-grid">
                <StationTable title="Zone PVC (Moyennes)" data={metrics.pvc} />
                <StationTable title="Zone ALU (Moyennes)" data={metrics.alu} />
            </div>

            <AlertList alerts={metrics.alerts} />
        </div>
    )
}

export default App
