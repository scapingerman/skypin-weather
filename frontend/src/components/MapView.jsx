import { useEffect, useRef } from 'react'
import L from 'leaflet'
import 'leaflet-draw'
import { riskColor } from '../utils'

// Fix default marker icon URLs
delete L.Icon.Default.prototype._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
})

export default function MapView({ zones, summaries, selectedId, onSelect, onPolygonDrawn }) {
  const mapRef = useRef(null)
  const drawnRef = useRef(null)
  const zonesLayerRef = useRef(null)

  // init
  useEffect(() => {
    if (mapRef.current) return
    const map = L.map('map', {
      center: [-34.6037, -58.3816], // Buenos Aires default
      zoom: 5,
      zoomControl: true,
    })

    // Dark basemap (CartoDB dark, free)
    L.tileLayer(
      'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
      {
        attribution:
          '© OpenStreetMap contributors · © CARTO',
        maxZoom: 19,
      }
    ).addTo(map)

    // Optional: Esri World Imagery (for satellite toggle later)
    const satLayer = L.tileLayer(
      'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
      { attribution: 'Tiles © Esri', maxZoom: 19 }
    )
    L.control.layers(
      {
        'Dark (CARTO)': map._layers[Object.keys(map._layers)[0]],
        'Satélite (Esri)': satLayer,
      },
      {},
      { position: 'topright', collapsed: true }
    ).addTo(map)

    // Draw controls
    const drawn = new L.FeatureGroup()
    map.addLayer(drawn)
    drawnRef.current = drawn

    // Localización de leaflet-draw al español (tooltips y botones in-draw)
    L.drawLocal.draw.handlers.polygon.tooltip.start = 'Click para empezar a dibujar la zona.'
    L.drawLocal.draw.handlers.polygon.tooltip.cont  = 'Click para agregar otro punto.'
    L.drawLocal.draw.handlers.polygon.tooltip.end   = 'Click en el primer punto para cerrar la zona.'
    L.drawLocal.draw.handlers.rectangle.tooltip.start = 'Click y arrastrá para dibujar un rectángulo.'
    L.drawLocal.draw.handlers.simpleshape.tooltip.end = 'Soltá el mouse para terminar.'
    L.drawLocal.draw.toolbar.actions.title = 'Cancelar dibujo'
    L.drawLocal.draw.toolbar.actions.text  = 'Cancelar'
    L.drawLocal.draw.toolbar.finish.title  = 'Finalizar dibujo'
    L.drawLocal.draw.toolbar.finish.text   = 'Finalizar'
    L.drawLocal.draw.toolbar.undo.title    = 'Borrar el último punto dibujado'
    L.drawLocal.draw.toolbar.undo.text     = 'Borrar último punto'
    L.drawLocal.edit.handlers.edit.tooltip.text    = 'Arrastrá los puntos o vértices para editar la zona.'
    L.drawLocal.edit.handlers.edit.tooltip.subtext = 'Click en Cancelar para descartar los cambios.'
    L.drawLocal.edit.handlers.remove.tooltip.text  = 'Click sobre una zona para borrarla.'
    L.drawLocal.edit.toolbar.actions.save.title   = 'Guardar cambios'
    L.drawLocal.edit.toolbar.actions.save.text    = 'Guardar'
    L.drawLocal.edit.toolbar.actions.cancel.title = 'Descartar cambios'
    L.drawLocal.edit.toolbar.actions.cancel.text  = 'Cancelar'
    L.drawLocal.edit.toolbar.actions.clearAll.title = 'Borrar todas las zonas'
    L.drawLocal.edit.toolbar.actions.clearAll.text  = 'Borrar todo'
    L.drawLocal.edit.toolbar.buttons.edit        = 'Editar zonas'
    L.drawLocal.edit.toolbar.buttons.editDisabled = 'No hay zonas para editar'
    L.drawLocal.edit.toolbar.buttons.remove       = 'Borrar zonas'
    L.drawLocal.edit.toolbar.buttons.removeDisabled = 'No hay zonas para borrar'
    L.drawLocal.draw.toolbar.buttons.polygon   = 'Dibujar una zona poligonal'
    L.drawLocal.draw.toolbar.buttons.rectangle = 'Dibujar una zona rectangular'

    // Patch: L.GeometryUtil.readableArea tira error con Leaflet 1.9+ cuando
    // leaflet-draw intenta mostrar el área en vivo. Sin este patch, el polígono
    // se rompe al 3er/4to punto. Mantenemos showArea activado ahora que es seguro.
    if (L.GeometryUtil && L.GeometryUtil.readableArea) {
      L.GeometryUtil.readableArea = function (area, isMetric, precision) {
        const p = L.Util.extend(
          { km: 2, ha: 2, m: 0, mi: 2, ac: 2, yd: 0, ft: 0, nm: 2 },
          precision || {}
        )
        if (isMetric) {
          if (area >= 1_000_000) return (area / 1_000_000).toFixed(p.km) + ' km²'
          if (area >= 10_000) return (area / 10_000).toFixed(p.ha) + ' ha'
          return area.toFixed(p.m) + ' m²'
        }
        const yd2 = area / 0.836127
        if (yd2 >= 3_097_600) return (yd2 / 3_097_600).toFixed(p.mi) + ' mi²'
        if (yd2 >= 4_840) return (yd2 / 4_840).toFixed(p.ac) + ' ac'
        return yd2.toFixed(p.yd) + ' yd²'
      }
    }

    const drawControl = new L.Control.Draw({
      position: 'topleft',
      edit: { featureGroup: drawn, remove: true },
      draw: {
        polygon: {
          allowIntersection: false,
          showArea: true,
          metric: true,
          shapeOptions: { color: '#4cc9f0', weight: 2, fillOpacity: 0.15 },
          // Asegurar que podés agregar tantos puntos como quieras
          maxPoints: 0,
        },
        rectangle: { shapeOptions: { color: '#4cc9f0', weight: 2 } },
        polyline: false,
        circle: false,
        marker: false,
        circlemarker: false,
      },
    })
    map.addControl(drawControl)

    map.on(L.Draw.Event.CREATED, (e) => {
      const layer = e.layer
      drawn.addLayer(layer)
      const gj = layer.toGeoJSON()
      onPolygonDrawn && onPolygonDrawn(gj.geometry)
    })

    zonesLayerRef.current = L.featureGroup().addTo(map)
    mapRef.current = map
  }, [])

  // draw zones whenever list changes
  useEffect(() => {
    const map = mapRef.current
    const layer = zonesLayerRef.current
    if (!map || !layer) return

    layer.clearLayers()

    summaries.forEach((s) => {
      const geo = L.geoJSON(s.zone.geometry, {
        style: () => ({
          color: riskColor(s.risk.level),
          weight: selectedId === s.zone.id ? 3 : 2,
          fillOpacity: selectedId === s.zone.id ? 0.35 : 0.18,
          dashArray: selectedId === s.zone.id ? null : '4,3',
        }),
      })
      geo.bindTooltip(
        `<b>${s.zone.name}</b><br/>Risk: ${s.risk.score} (${s.risk.level})<br/>NDVI: ${s.metrics.ndvi}`,
        { sticky: true, direction: 'top' }
      )
      geo.on('click', () => onSelect && onSelect(s.zone.id))
      layer.addLayer(geo)
    })

    if (summaries.length && !selectedId) {
      try { map.fitBounds(layer.getBounds().pad(0.2)) } catch {}
    }
  }, [summaries, selectedId, onSelect])

  return <div id="map" role="region" aria-label="Mapa interactivo" />
}
