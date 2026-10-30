import { useAccuracy } from '../api/queries'
import BarPanel from '../components/BarPanel'
import { ErrorBox, Loading } from '../components/QueryState'
import StatStrip from '../components/StatStrip'
import { dayCounts, leanOf } from '../lib/accuracy'
import { formatDay, formatMW } from '../lib/format'

const RED = '#e4002b'
const BLACK = '#000000'

const mw = (value) => (value == null ? '-' : `${formatMW(value)} MW`)

const VERDICT = {
  high: 'Forecasts ran higher than actual wind. Treat the headline forecast as optimistic and plan around the "Count on at least" figure.',
  low: 'Forecasts ran lower than actual wind, so plans based on them were on the cautious side.',
  balanced: 'Forecasts were not clearly too high or too low overall. The misses went both ways.',
  unknown: '',
}

const LEAN_LABEL = { high: 'Too high', low: 'Too low', balanced: 'Balanced', unknown: '-' }

function statItems(report, lean) {
  const { summary } = report
  const days = dayCounts(report.by_day)
  const pct =
    summary.mae_pct_of_mean_actual == null ? null : Math.round(summary.mae_pct_of_mean_actual)
  return [
    {
      label: 'Average miss',
      value: mw(summary.mae_mw),
      hint: pct == null ? undefined : `About ${pct}% of average wind output`,
    },
    {
      label: 'The forecast leaned',
      value: LEAN_LABEL[lean],
      hint: `${mw(Math.abs(summary.bias_mw ?? 0))} on average; too high on ${days.tooHigh} of ${days.total} days`,
      tone: lean === 'high' ? 'brand' : undefined,
    },
    {
      label: 'Rarely worse than',
      value: mw(summary.p90_abs_error_mw),
      hint: '9 hours in 10 missed by less than this',
    },
    {
      label: 'Hours compared',
      value: formatMW(summary.n_compared),
      hint: `${formatMW(summary.n_missing_actual)} hours had no actual data`,
    },
  ]
}

function Panel({ title, children, intro }) {
  return (
    <section className="mt-10">
      <h3 className="text-lg font-bold">{title}</h3>
      <p className="mt-1 max-w-3xl text-sm text-neutral-600">{intro}</p>
      <div className="mt-3">{children}</div>
    </section>
  )
}

function DetailTable({ summary }) {
  const rows = [
    ['Average miss (MAE)', mw(summary.mae_mw), 'Average size of the error, ignoring direction.'],
    ['Typical miss (median)', mw(summary.p50_abs_error_mw), 'Half of all hours were closer than this.'],
    ['Large miss (90th percentile)', mw(summary.p90_abs_error_mw), '9 hours in 10 were closer than this.'],
    ['Worst 5% start at', mw(summary.p95_abs_error_mw), 'Only 1 hour in 20 missed by more than this.'],
    ['Root-mean-square error', mw(summary.rmse_mw), 'Like the average miss, but punishes big misses more.'],
    ['Lean (bias)', mw(summary.bias_mw), 'Average of forecast minus actual. Positive means too high.'],
    [
      'Middle 80% of errors',
      `${mw(summary.p10_error_mw)} to ${mw(summary.p90_error_mw)}`,
      'The "likely range" on the plan page is built from this.',
    ],
  ]
  return (
    <table className="w-full text-left text-sm">
      <thead>
        <tr className="border-b-2 border-black">
          <th className="py-2 pr-4 font-bold">Measure</th>
          <th className="py-2 pr-4 text-right font-bold">Value</th>
          <th className="py-2 font-bold">What it means</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(([name, value, meaning]) => (
          <tr key={name} className="border-b border-neutral-200">
            <td className="py-2 pr-4">{name}</td>
            <td className="py-2 pr-4 text-right font-semibold">{value}</td>
            <td className="py-2 text-neutral-600">{meaning}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export default function AccuracyPage() {
  const accuracy = useAccuracy()
  if (accuracy.isPending) return <Loading />
  if (accuracy.isError) return <ErrorBox error={accuracy.error} />

  const report = accuracy.data
  const { summary } = report

  if (summary.n_compared === 0) {
    return (
      <div>
        <h2 className="display text-3xl">How accurate were the forecasts?</h2>
        <p className="mt-6 border-l-4 border-brand bg-neutral-100 p-4">
          No hours could be compared with actual wind data yet.
        </p>
      </div>
    )
  }

  const lean = leanOf(summary)

  return (
    <div>
      <h2 className="display max-w-3xl text-3xl">How accurate were the forecasts?</h2>
      <p className="mt-3 max-w-2xl text-neutral-700">
        Every hour from {formatDay(report.first_delivery_date)} to{' '}
        {formatDay(report.last_delivery_date)}, compared with what wind actually produced. We used
        the forecast the buyer had at the {report.cutoff_local} cutoff, not a later one.
      </p>
      {VERDICT[lean] && (
        <p className="mt-4 max-w-2xl border-l-4 border-brand bg-neutral-100 p-4 font-semibold">
          {VERDICT[lean]}
        </p>
      )}

      <StatStrip items={statItems(report, lean)} />

      <Panel
        title="Day by day: forecast minus actual"
        intro="Red bars: the forecast was too high that day. Black bars: too low. A bar at zero means a perfect day."
      >
        <BarPanel
          title="Average forecast error for each day"
          data={report.by_day}
          valueKey="bias_mw"
          valueName="Average error"
          signed
          colorOf={(value) => (value > 0 ? RED : BLACK)}
          tickOf={(label) => String(Number(label.slice(8)))}
          titleOf={formatDay}
        />
      </Panel>

      <Panel
        title="Does an earlier forecast do worse?"
        intro="Average miss by how long before the hour the forecast was published. This uses every published forecast, not only the one available at the cutoff."
      >
        <BarPanel
          title="Average miss by forecast age"
          data={report.by_horizon}
          valueKey="mae_mw"
          valueName="Average miss"
          titleOf={(label) => `Published ${label} before the hour`}
        />
      </Panel>

      <Panel
        title="Which hours of the day are hardest?"
        intro="Average miss for each hour of the day, across the whole period."
      >
        <BarPanel
          title="Average miss by hour of day"
          data={report.by_hour}
          valueKey="mae_mw"
          valueName="Average miss"
          tickOf={(label) => `${label}`}
          titleOf={(label) => `${label}:00`}
        />
      </Panel>

      <details className="mt-10 border-t border-neutral-300 pt-4">
        <summary className="cursor-pointer font-semibold">All measures, for analysts</summary>
        <div className="mt-3 overflow-x-auto">
          <DetailTable summary={summary} />
          <p className="mt-3 max-w-3xl text-sm text-neutral-600">
            {formatMW(report.n_published_after_target)} forecast rows were published after the hour
            they describe. They are stored but excluded from every figure on this page.
          </p>
        </div>
      </details>
    </div>
  )
}
