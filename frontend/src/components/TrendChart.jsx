import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid,
} from 'recharts'
import { shortDate } from '../utils'

export default function TrendChart({ title, data, color = '#4cc9f0', domain, unit = '' }) {
  const trimmed = (data || []).map((p) => ({ d: shortDate(p.date), v: p.value }))

  return (
    <div className="card" style={{ gridColumn: '1 / -1' }}>
      <h4>{title}</h4>
      <div style={{ width: '100%', height: 120 }}>
        <ResponsiveContainer>
          <LineChart data={trimmed} margin={{ top: 8, right: 10, left: -20, bottom: 0 }}>
            <CartesianGrid stroke="#1c2530" strokeDasharray="3 3" />
            <XAxis
              dataKey="d"
              tick={{ fontSize: 10, fill: '#6f7b8c' }}
              interval={Math.max(0, Math.floor(trimmed.length / 6) - 1)}
              stroke="#242d3a"
            />
            <YAxis
              tick={{ fontSize: 10, fill: '#6f7b8c' }}
              domain={domain || ['auto', 'auto']}
              stroke="#242d3a"
              width={42}
            />
            <Tooltip
              contentStyle={{
                background: '#161d26',
                border: '1px solid #242d3a',
                borderRadius: 6,
                fontSize: 12,
                color: '#e6edf3',
              }}
              formatter={(v) => [`${v}${unit}`, title]}
            />
            <Line
              type="monotone"
              dataKey="v"
              stroke={color}
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
