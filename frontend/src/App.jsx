import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from './api/client'
import MapView from './components/MapView'
import SidePanel from './components/SidePanel'
import ZoneTable from './components/ZoneTable'
import TrendChart from './components/TrendChart'
import ErrorBoundary from './components/ErrorBoundary'

export default function App() {
  const [summaries, setSummaries] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [toast, setToast] = useState(null)
  const [apiHealthy, setApiHealthy] = useState(null)

  const refresh = useCallback(async () => {
    try {
      const data = await api.summary()
      setSummaries(data)
    } catch (e) {
      console.error(e)
      setToast(`Error cargando zonas: ${e.message}`)
    }
  }, [])

  useEffect(() => {
    api.health().then(setApiHealthy).catch(() => setApiHealthy(false))
    refresh()
  }, [refresh])

  const handlePolygon = useCallback(
    async (geometry) => {
      const name = prompt('Nombre de la zona:', `Zona ${summaries.length + 1}`)
      if (!name) return
      try {
        const z = await api.createZone(name, geometry)
        setSelectedId(z.id)
        setToast(`Zona "${name}" creada (${z.area_ha} ha)`)
        await refresh()
      } catch (e) {
        setToast(`No se pudo crear la zona: ${e.message}`)
      }
    },
    [summaries.length, refresh]
  )

  const handleDelete = useCallback(
    async (id) => {
      if (!confirm('¿Eliminar esta zona?')) return
      try {
        await api.deleteZone(id)
        setSelectedId(null)
        setToast('Zona eliminada')
        await refresh()
      } catch (e) {
        setToast(`Error al eliminar: ${e.message}`)
      }
    },
    [refresh]
  )

  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(null), 3000)
    return () => clearTimeout(t)
  }, [toast])

  const selected = useMemo(
    () => summaries.find((s) => s.zone.id === selectedId) || null,
    [summaries, selectedId]
  )

  // Aggregated NDVI trend: promedio por fecha entre todas las zonas.
  // OJO: cada zona puede tener su propia cantidad de observaciones
  // (mock=30 diarios, sentinel=4-8 por mes), así que agrupamos por fecha
  // y promediamos solo los que tengan dato ese día.
  const aggTrend = useMemo(() => {
    if (summaries.length === 0) return []
    const byDate = new Map() // date -> [values...]
    for (const s of summaries) {
      const trend = s?.metrics?.ndvi_trend || []
      for (const p of trend) {
        if (!p || typeof p.value !== 'number' || !p.date) continue
        if (!byDate.has(p.date)) byDate.set(p.date, [])
        byDate.get(p.date).push(p.value)
      }
    }
    return Array.from(byDate.entries())
      .sort((a, b) => (a[0] < b[0] ? -1 : 1))
      .map(([date, vals]) => ({
        date,
        value: +(vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(3),
      }))
  }, [summaries])

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <div className="brand-logo">S</div>
          <div>
            <span className="brand-name">Skyping Weather</span>
            <span className="brand-sub">MVP · mapa + NDVI + riesgo</span>
          </div>
        </div>
        <div className="topbar-actions">
          <span
            className="tenant-badge"
            title="Tenant actual"
            style={{
              borderColor:
                apiHealthy === true
                  ? '#06d6a0'
                  : apiHealthy === false
                  ? '#ef476f'
                  : undefined,
            }}
          >
            tenant: demo · api:{' '}
            {apiHealthy === null ? '…' : apiHealthy ? 'ok' : 'down'}
          </span>
          <button className="btn" onClick={refresh}>Refrescar</button>
        </div>
      </header>

      <div className="main">
        <div className="map-wrap">
          <ErrorBoundary>
            <MapView
              zones={summaries.map((s) => s.zone)}
              summaries={summaries}
              selectedId={selectedId}
              onSelect={setSelectedId}
              onPolygonDrawn={handlePolygon}
            />
          </ErrorBoundary>
        </div>

        <aside className="side">
          <ErrorBoundary>
            <SidePanel summary={selected} onDelete={handleDelete} />
          </ErrorBoundary>
        </aside>

        <div className="bottom">
          <div>
            <h3>Zonas ({summaries.length})</h3>
            <ErrorBoundary>
              <ZoneTable
                summaries={summaries}
                selectedId={selectedId}
                onSelect={setSelectedId}
              />
            </ErrorBoundary>
          </div>
          <div>
            <h3>Tendencia agregada NDVI</h3>
            <ErrorBoundary>
              {aggTrend.length === 0 ? (
                <div className="empty" style={{ padding: 0 }}>
                  Creá al menos una zona para ver tendencias.
                </div>
              ) : (
                <TrendChart
                  title="Promedio NDVI (todas las zonas)"
                  data={aggTrend}
                  domain={[-0.1, 0.9]}
                  color="#4cc9f0"
                />
              )}
            </ErrorBoundary>
          </div>
        </div>
      </div>

      {toast && <div className="toast">{toast}</div>}
    </div>
  )
}
