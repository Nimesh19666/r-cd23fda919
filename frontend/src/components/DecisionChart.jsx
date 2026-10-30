import { useMemo } from 'react'
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { formatDateTime, formatHours, formatMW, formatTime } from '../lib/format'

const RED = '#E4002B'
const BLACK = '#000000'
const AXIS_TEXT = { fill: '#525252', fontSize: 12 }

// Merge the hourly forecast points and the half-hourly actuals onto one time axis.
function buildSeries(points, actuals) {
  const byTime = new Map()
  for (const p of points) {
    const t = Date.parse(p.start_time)
    byTime.set(t, {
      t,
      forecast: p.forecast_mw,
      range: p.range_low_mw == null ? null : [p.range_low_mw, p.range_high_mw],
      publishTime: p.publish_time,
      horizon: p.horizon_hours,
    })
  }
  for (const a of actuals) {
    const t = Date.parse(a.start_time)
    const row = byTime.get(t) ?? { t }
    row.actual = a.actual_mw
    byTime.set(t, row)
  }
  return [...byTime.values()].sort((x, y) => x.t - y.t)
}

function ChartTooltip({ active, payload, tz }) {
  if (!active || !payload || payload.length === 0) return null
  const row = payload[0].payload
  return (
    <div className="border border-black bg-white p-3 text-sm">
      <p className="font-bold">{formatTime(row.t, tz)}</p>
      {row.forecast != null && (
        <>
          <p>Forecast: {formatMW(row.forecast)} MW</p>
          {row.range && (
            <p>
              Typical range: {formatMW(row.range[0])} to {formatMW(row.range[1])} MW
            </p>
          )}
          <p className="text-neutral-600">
            Published {formatDateTime(row.publishTime, tz)} ({formatHours(row.horizon)} h ahead)
          </p>
        </>
      )}
      {row.actual != null && <p>Actual: {formatMW(row.actual)} MW</p>}
    </div>
  )
}

export default function DecisionChart({ points, actuals, showActuals, tz }) {
  const series = useMemo(() => buildSeries(points, actuals), [points, actuals])

  // A tick every 3 hours, on the hour, in market time.
  const ticks = useMemo(
    () =>
      series
        .map((row) => row.t)
        .filter((t) => {
          const [hour, minute] = formatTime(t, tz).split(':').map(Number)
          return minute === 0 && hour % 3 === 0
        }),
    [series, tz],
  )

  return (
    <div className="h-96 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={series} margin={{ top: 10, right: 20, bottom: 10, left: 10 }}>
          <CartesianGrid stroke="#e5e5e5" vertical={false} />
          <XAxis
            dataKey="t"
            type="number"
            scale="time"
            domain={['dataMin', 'dataMax']}
            ticks={ticks}
            tickFormatter={(t) => formatTime(t, tz)}
            tick={AXIS_TEXT}
            axisLine={{ stroke: BLACK }}
            tickLine={{ stroke: BLACK }}
          />
          <YAxis
            domain={[0, 'auto']}
            width={70}
            tickFormatter={(v) => v.toLocaleString('en-GB')}
            tick={AXIS_TEXT}
            axisLine={false}
            tickLine={false}
            label={{ value: 'MW', angle: -90, position: 'insideLeft', fill: '#525252' }}
          />
          <Tooltip content={<ChartTooltip tz={tz} />} cursor={{ stroke: BLACK, strokeWidth: 1 }} />
          <Legend
            wrapperStyle={{ paddingTop: 12 }}
            formatter={(value) => <span style={{ color: BLACK }}>{value}</span>}
          />
          <Area
            dataKey="range"
            name="Likely range of actual wind"
            stroke="none"
            fill={RED}
            fillOpacity={0.12}
            connectNulls
            isAnimationActive={false}
          />
          <Line
            dataKey="forecast"
            name="Forecast known at cutoff"
            stroke={RED}
            strokeWidth={3}
            dot={{ r: 4, fill: RED, stroke: '#fff', strokeWidth: 2 }}
            activeDot={{ r: 6, fill: RED, stroke: '#fff', strokeWidth: 2 }}
            connectNulls
            isAnimationActive={false}
          />
          {showActuals && (
            <Line
              dataKey="actual"
              name="Actual wind (known only afterwards)"
              stroke={BLACK}
              strokeWidth={2}
              strokeDasharray="6 4"
              dot={false}
              activeDot={{ r: 4, fill: BLACK, stroke: '#fff', strokeWidth: 2 }}
              connectNulls
              isAnimationActive={false}
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}
