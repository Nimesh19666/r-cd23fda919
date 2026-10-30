import { formatDateTime, formatDay } from '../lib/format'

function Block({ title, children }) {
  return (
    <section className="border-t-2 border-black pt-4">
      <h3 className="text-lg font-bold">{title}</h3>
      <div className="mt-2 max-w-3xl space-y-2 text-neutral-700">{children}</div>
    </section>
  )
}

export default function AssumptionsPage({ meta }) {
  const tz = meta.timezone
  return (
    <div>
      <h2 className="display max-w-3xl text-3xl">Assumptions and limits</h2>
      <p className="mt-3 max-w-2xl text-neutral-700">
        What this portal assumes, how the numbers are made, and what you should not read into them.
      </p>

      <div className="mt-8 space-y-8">
        <Block title="Which forecast the plan uses">
          <p>
            For each hour of the delivery day we show the most recent forecast published at or
            before {meta.cutoff_local} ({tz} time) on the day before. Forecasts published later are
            ignored, so the plan never uses anything the buyer could not have known at the time.
          </p>
        </Block>

        <Block title="The cutoff is our assumption">
          <p>
            The brief does not say when the day-ahead decision is made. We used {meta.cutoff_local}{' '}
            ({tz}) on the previous day. It is a single setting and can be changed without touching
            the code.
          </p>
          <p>
            Purchase decisions covered: {formatDay(meta.decision_start_date)} to{' '}
            {formatDay(meta.decision_end_date)}. That means delivery days from{' '}
            {formatDay(meta.first_delivery_date)} to {formatDay(meta.last_delivery_date)}.
          </p>
        </Block>

        <Block title="How accuracy is measured">
          <p>{meta.error_definition}</p>
          <p>
            Forecasts are hourly and actual wind is recorded every half hour, so we compare only at
            the hour marks where both exist. An hour with no actual is counted as missing, never as
            zero.
          </p>
        </Block>

        <Block title="The likely range and the cautious figure">
          <p>
            The likely range is the middle 80% of January's forecast errors, placed around each
            forecast. "Count on at least" is the low end of that range, averaged over the day.
          </p>
          <p>
            The range is worked out from the same month it is judged on, so it looks a little better
            than it would on a month it had never seen. A fairer test would build it from earlier
            months.
          </p>
        </Block>

        <Block title="Known limits">
          <p>
            Forecasts ran higher than actual wind in this period. We checked that this is not a
            timing slip, but we have not established the cause. One possibility is that the actual
            wind series does not include every wind farm. That is unverified.
          </p>
          <p>
            This is one winter month. Accuracy in a calm summer month could look quite different.
          </p>
        </Block>

        <Block title="Data">
          <ul className="list-disc space-y-1 pl-5">
            {meta.notes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
          <p>
            Actual wind data runs to {formatDateTime(meta.actuals_last_time, tz)}. The latest forecast
            on file was published {formatDateTime(meta.forecasts_last_publish_time, tz)}.
          </p>
        </Block>
      </div>
    </div>
  )
}
