import MetricsCard from './MetricsCard'
import TrendChart from './TrendChart'
import { fmt, ndviColor } from '../utils'

export default function SidePanel({ summary, onDelete }) {
  if (!summary) {
    return (
      <div className="empty">
        <strong>Aún no seleccionaste una zona</strong>
        Dibujá un polígono en el mapa o elegí una del panel inferior para ver sus métricas.
      </div>
    )
  }

  const { zone, metrics, risk } = summary

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <div style={{ fontSize: 16, fontWeight: 600 }}>{zone.name}</div>
          <div style={{ fontSize: 11, color: '#6f7b8c', fontFamily: 'var(--mono)' }}>
            {zone.area_ha.toFixed(1)} ha · {zone.centroid[1].toFixed(3)}, {zone.centroid[0].toFixed(3)}
          </div>
        </div>
        <button className="btn danger" onClick={() => onDelete(zone.id)}>Eliminar</button>
      </div>

      <h3 style={{ marginTop: 16 }}>Resumen de riesgo</h3>
      <div className="card risk-card">
        <div className="risk-score">
          <div className="big">{fmt(risk.score, 0)}</div>
          <span className={`risk-level ${risk.level}`}>{risk.level}</span>
        </div>
        <div className="recommendation">{risk.recommendation}</div>
        <div style={{ marginTop: 10 }}>
          {risk.drivers.map((d) => (
            <div key={d.name} className="driver-row">
              <span style={{ flex: '0 0 46%', fontSize: 11, color: '#a8b3c2' }}>
                {d.name}
              </span>
              <div className="bar">
                <span style={{ width: `${Math.min(100, d.contribution * 3)}%` }} />
              </div>
              <span className="contrib">{d.contribution}</span>
            </div>
          ))}
        </div>
      </div>

      <h3 style={{ marginTop: 16 }}>Métricas actuales</h3>
      <div className="metric-grid">
        <MetricsCard
          title="NDVI"
          value={metrics.ndvi}
          hint="Índice de vegetación (-0.1 a 0.9)"
          color={ndviColor(metrics.ndvi)}
          source={metrics.sources?.ndvi}
        />
        <MetricsCard
          title="Humedad suelo"
          value={metrics.soil_moisture}
          unit="%"
          hint="Volumétrica 0-27 cm (raíces)"
          source={metrics.sources?.soil_moisture}
        />
        <MetricsCard
          title="Precipitación 7d"
          value={metrics.precipitation_mm_7d}
          unit=" mm"
          hint="Acumulado última semana"
          source={metrics.sources?.precipitation}
        />
        <MetricsCard
          title="Temperatura"
          value={metrics.temperature_c}
          unit=" °C"
          hint="Actual a 2m"
          source={metrics.sources?.temperature}
        />
        <MetricsCard
          title="Viento"
          value={metrics.wind_kmh}
          unit=" km/h"
          hint="Actual a 10m"
          source={metrics.sources?.wind}
        />
        <MetricsCard
          title="Actualizado"
          value={new Date(metrics.updated_at).toLocaleTimeString()}
          hint="UTC"
        />
      </div>
      <div className="data-attribution">
        NDVI: <a href="https://www.sentinel-hub.com" target="_blank" rel="noreferrer">Sentinel-2 L2A</a> ·
        Humedad suelo (ERA5-Land) y clima vía{' '}
        <a href="https://open-meteo.com" target="_blank" rel="noreferrer">Open-Meteo</a>.
        NDVI se calcula como media sobre el polígono de los últimos 30 días,
        descartando píxeles con nube/sombra/nieve.
      </div>

      <h3 style={{ marginTop: 16 }}>Tendencias (30 días)</h3>
      <div className="metric-grid">
        <TrendChart
          title="NDVI"
          data={metrics.ndvi_trend}
          domain={[-0.1, 0.9]}
          color="#06d6a0"
        />
        <TrendChart
          title="Humedad de suelo (%)"
          data={metrics.soil_moisture_trend}
          domain={[0, 60]}
          color="#4cc9f0"
          unit="%"
        />
      </div>
    </div>
  )
}
