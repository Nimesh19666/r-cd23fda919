import { useState } from 'react'
import { useDecision } from '../api/queries'
import DecisionChart from '../components/DecisionChart'
import DecisionTable from '../components/DecisionTable'
import { ErrorBox, Loading } from '../components/QueryState'
import StatStrip from '../components/StatStrip'
import { outcomeSummary, planSummary } from '../lib/decision'
import { addDays, clampDate, formatDateTime, formatDay, formatHours, formatMW } from '../lib/format'

const PREFERRED_DEFAULT = '2026-01-15'

const stepButton =
  'border border-black px-3 py-2 hover:bg-black hover:text-white disabled:opacity-30 ' +
  'disabled:hover:bg-white disabled:hover:text-black'

function planItems(plan, tz) {
  return [
    {
      label: 'Count on at least',
      value: plan.countOnAtLeast == null ? '-' : `${formatMW(plan.countOnAtLeast)} MW`,
      hint: 'A cautious daily average. In January, wind reached its hourly figure about 9 hours in 10.',
      tone: 'brand',
    },
    {
      label: 'Forecast average',
      value: `${formatMW(plan.forecastAverage)} MW`,
      hint: `Across ${plan.hours} hours of the day`,
    },
    {
      label: 'Latest forecast used',
      value: formatDateTime(plan.latestPublished, tz),
      hint: `${plan.versions} ${plan.versions === 1 ? 'version' : 'versions'}, ${formatHours(plan.minAhead)} to ${formatHours(plan.maxAhead)} hours before each hour`,
    },
  ]
}

function outcomeItems(outcome) {
  const gap = Math.round(outcome.forecastAverage - outcome.actualAverage)
  let verdict = 'On target'
  if (gap > 0) verdict = `${formatMW(gap)} MW too high`
  if (gap < 0) verdict = `${formatMW(-gap)} MW too low`
  return [
    {
      label: 'Actual wind',
      value: `${formatMW(outcome.actualAverage)} MW`,
      hint: `Average across ${outcome.hoursCompared} hours`,
    },
    {
      label: 'The forecast was',
      value: verdict,
      hint: 'On average over the day',
      tone: gap > 0 ? 'brand' : undefined,
    },
    {
      label: 'Cautious figure held',
      value: `${outcome.floorHeld} of ${outcome.floorChecked} hours`,
      hint: 'Hours when wind was at or above the figure to count on',
    },
  ]
}

export default function DecisionPage({ meta }) {
  const tz = meta.timezone
  const first = meta.first_delivery_date
  const last = meta.last_delivery_date
  const [date, setDate] = useState(clampDate(PREFERRED_DEFAULT, first, last))
  // Remember WHICH day was revealed, so every new day starts hidden again.
  const [revealedDate, setRevealedDate] = useState(null)
  const revealed = revealedDate === date

  const decision = useDecision(date)
  const data = decision.data
  const plan = data ? planSummary(data.points) : null
  const outcome = data && revealed ? outcomeSummary(data.points) : null

  return (
    <div>
      <h2 className="display max-w-3xl text-3xl">Plan for {formatDay(date)}</h2>
      <p className="mt-3 max-w-2xl text-neutral-700">
        {data
          ? `Based on the latest wind forecast published before ${formatDateTime(data.cutoff_utc, tz)}, the cutoff for day-ahead buying. What happened afterwards stays hidden until you ask for it.`
          : 'Based on the latest wind forecast published before the day-ahead cutoff.'}
      </p>

      <div className="mt-6 flex items-stretch">
        <button
          type="button"
          className={stepButton}
          disabled={date <= first}
          onClick={() => setDate(addDays(date, -1))}
          aria-label="Previous day"
        >
          &larr;
        </button>
        <label className="flex items-center gap-2 border-y border-black px-3">
          <span className="text-sm text-neutral-600">Delivery day</span>
          <input
            type="date"
            className="bg-transparent py-2 font-semibold"
            value={date}
            min={first}
            max={last}
            onChange={(event) => event.target.value && setDate(event.target.value)}
          />
        </label>
        <button
          type="button"
          className={stepButton}
          disabled={date >= last}
          onClick={() => setDate(addDays(date, 1))}
          aria-label="Next day"
        >
          &rarr;
        </button>
      </div>

      {decision.isPending && <Loading />}
      {decision.isError && (
        <div className="mt-6">
          <ErrorBox error={decision.error} />
        </div>
      )}

      {data && (
        <div className={decision.isPlaceholderData ? 'opacity-50 transition-opacity' : ''}>
          {plan ? (
            <StatStrip items={planItems(plan, tz)} />
          ) : (
            <p className="mt-8 border-l-4 border-brand bg-neutral-100 p-4">
              No forecast had been published before the cutoff for this day.
            </p>
          )}

          <section className="mt-10">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <h3 className="text-lg font-bold">Forecast for the day</h3>
              <button
                type="button"
                onClick={() => setRevealedDate(revealed ? null : date)}
                className={
                  revealed
                    ? 'border border-black px-4 py-2 font-semibold hover:bg-black hover:text-white'
                    : 'bg-brand px-4 py-2 font-semibold text-white hover:bg-black'
                }
              >
                {revealed ? 'Hide what actually happened' : 'Reveal what actually happened'}
              </button>
            </div>
            <div className="mt-3">
              <DecisionChart
                points={data.points}
                actuals={data.actuals}
                showActuals={revealed}
                tz={tz}
              />
            </div>
          </section>

          {revealed && (
            <section>
              {outcome ? (
                <StatStrip items={outcomeItems(outcome)} />
              ) : (
                <p className="mt-6 border-l-4 border-brand bg-neutral-100 p-4">
                  No actual wind data is available for this day.
                </p>
              )}
            </section>
          )}

          <section className="mt-10">
            <h3 className="mb-3 text-lg font-bold">Hour by hour</h3>
            <DecisionTable points={data.points} tz={tz} revealed={revealed} />
          </section>

          <details className="mt-10 border-t border-neutral-300 pt-4">
            <summary className="cursor-pointer font-semibold">How is this calculated?</summary>
            <div className="mt-3 max-w-3xl space-y-2 text-sm text-neutral-700">
              <p>
                For each hour we use the latest forecast published at or before the cutoff. Later
                forecasts are ignored, because the buyer could not have seen them.
              </p>
              <p>
                {data.range_note} Count on at least is the low end of this likely range, averaged
                over the day.
              </p>
              <p>{meta.error_definition}</p>
            </div>
          </details>
        </div>
      )}
    </div>
  )
}
