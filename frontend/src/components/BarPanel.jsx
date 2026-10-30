import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { formatMW } from '../lib/format'

const BLACK = '#000000'
const TICK = { fontSize: 12, fill: '#525252' }

function ChartTooltip({ active, payload, valueKey, valueName, signed, titleOf }) {
  if (!active || !payload?.length) return null
  const row = payload[0].payload
  return (
    <div className="border border-black bg-white p-3 text-sm">
      <p className="font-bold">{titleOf(row.label)}</p>
      <p>
        {valueName}: {formatMW(row[valueKey], { sign: signed })} MW
      </p>
      <p className="text-neutral-600">{formatMW(row.n_compared)} hours compared</p>
    </div>
  )
}

// One bar per group (day, hour of day, forecast age). `colorOf` can colour bars by value.
export default function BarPanel({
  title,
  data,
  valueKey,
  valueName,
  signed = false,
  tickOf = (label) => label,
  titleOf = (label) => label,
  colorOf,
}) {
  return (
    <div role="img" aria-label={title} className="h-72 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
          <CartesianGrid vertical={false} stroke="#e5e5e5" />
          <XAxis dataKey="label" tickFormatter={tickOf} tick={TICK} tickLine={false} />
          <YAxis
            tick={TICK}
            tickLine={false}
            axisLine={false}
            width={56}
            tickFormatter={(value) => value.toLocaleString('en-GB')}
          />
          <Tooltip
            cursor={{ fill: '#f5f5f5' }}
            content={
              <ChartTooltip
                valueKey={valueKey}
                valueName={valueName}
                signed={signed}
                titleOf={titleOf}
              />
            }
          />
          {signed && <ReferenceLine y={0} stroke={BLACK} />}
          <Bar dataKey={valueKey} isAnimationActive={false}>
            {data.map((row) => (
              <Cell key={row.label} fill={colorOf ? colorOf(row[valueKey]) : BLACK} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
