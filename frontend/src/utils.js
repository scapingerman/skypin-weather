export const riskColor = (level) => {
  switch (level) {
    case 'low': return '#06d6a0'
    case 'medium': return '#ffd166'
    case 'high': return '#ef476f'
    case 'critical': return '#d90429'
    default: return '#6f7b8c'
  }
}

export const ndviColor = (v) => {
  // v in [-0.1, 0.9]
  if (v < 0.1) return '#a85c32'
  if (v < 0.25) return '#c98a4b'
  if (v < 0.4) return '#d9c06a'
  if (v < 0.55) return '#9fc26c'
  if (v < 0.7) return '#4e9a3f'
  return '#1f6b2a'
}

export const fmt = (v, d = 2) =>
  v === null || v === undefined || Number.isNaN(v) ? '—' : Number(v).toFixed(d)

export const shortDate = (iso) => {
  const d = new Date(iso)
  return `${String(d.getMonth() + 1).padStart(2, '0')}/${String(d.getDate()).padStart(2, '0')}`
}
