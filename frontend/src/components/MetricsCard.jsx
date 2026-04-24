import { fmt } from '../utils'

const SOURCE_META = {
  'open-meteo': { label: 'LIVE', cls: 'real', title: 'Dato real (Open-Meteo)' },
  'era5-land':  { label: 'LIVE', cls: 'real', title: 'Dato real (ERA5-Land vía Open-Meteo)' },
  'sentinel-2': { label: 'LIVE', cls: 'real', title: 'Dato real (Sentinel-2 L2A, promedio sobre el polígono)' },
  'smap':       { label: 'LIVE', cls: 'real', title: 'Dato real (SMAP)' },
  'mock':       { label: 'DEMO', cls: 'mock', title: 'Valor simulado (mock)' },
}

export default function MetricsCard({ title, value, unit, hint, color, source }) {
  const meta = SOURCE_META[source] || null

  return (
    <div className="card">
      <h4>
        <span>{title}</span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          {meta && (
            <span className={`source-badge ${meta.cls}`} title={meta.title}>
              {meta.label}
            </span>
          )}
          {color && (
            <span
              style={{
                display: 'inline-block',
                width: 10, height: 10, borderRadius: 2,
                background: color,
              }}
            />
          )}
        </span>
      </h4>
      <div className="value">
        {typeof value === 'number' ? fmt(value, 2) : value}
        {unit && <span className="unit">{unit}</span>}
      </div>
      {hint && <div className="sub">{hint}</div>}
    </div>
  )
}
