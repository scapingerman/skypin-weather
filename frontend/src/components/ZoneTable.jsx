import { fmt } from '../utils'

export default function ZoneTable({ summaries, selectedId, onSelect }) {
  if (!summaries || summaries.length === 0) {
    return (
      <div className="empty" style={{ padding: 0 }}>
        <strong>Sin zonas todavía</strong>
        Dibujá un polígono sobre el mapa para crear la primera.
      </div>
    )
  }

  return (
    <table className="zones">
      <thead>
        <tr>
          <th>Zona</th>
          <th>Área (ha)</th>
          <th>NDVI</th>
          <th>Hum. suelo (%)</th>
          <th>Precip 7d (mm)</th>
          <th>Temp (°C)</th>
          <th>Riesgo</th>
        </tr>
      </thead>
      <tbody>
        {summaries.map((s) => (
          <tr
            key={s.zone.id}
            className={selectedId === s.zone.id ? 'selected' : ''}
            onClick={() => onSelect(s.zone.id)}
          >
            <td>{s.zone.name}</td>
            <td className="mono">{fmt(s.zone.area_ha, 1)}</td>
            <td className="mono">{fmt(s.metrics.ndvi, 2)}</td>
            <td className="mono">{fmt(s.metrics.soil_moisture, 1)}</td>
            <td className="mono">
              {fmt(s.metrics.precipitation_mm_7d, 1)}
              {s.metrics.sources?.precipitation === 'open-meteo' && (
                <span className="source-badge real" style={{ marginLeft: 6 }}>LIVE</span>
              )}
            </td>
            <td className="mono">
              {fmt(s.metrics.temperature_c, 1)}
              {s.metrics.sources?.temperature === 'open-meteo' && (
                <span className="source-badge real" style={{ marginLeft: 6 }}>LIVE</span>
              )}
            </td>
            <td className="mono">
              <span className={`level-dot ${s.risk.level}`} />
              {fmt(s.risk.score, 0)} · {s.risk.level}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
