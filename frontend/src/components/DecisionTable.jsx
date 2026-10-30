import { formatDateTime, formatHours, formatMW, formatTime } from '../lib/format'

// Over-forecast is red, under-forecast is black; the sign is always printed too.
function errorClass(error) {
  return error > 0 ? 'font-semibold text-brand' : 'font-semibold'
}

export default function DecisionTable({ points, tz, revealed }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        {revealed && (
          <caption className="pb-3 text-left text-neutral-600">
            Error is forecast minus actual. A plus sign means the forecast was too high.
          </caption>
        )}
        <thead>
          <tr className="border-b-2 border-black">
            <th className="py-2 pr-4 font-bold">Time</th>
            <th className="py-2 pr-4 text-right font-bold">Forecast (MW)</th>
            <th className="py-2 pr-4 text-right font-bold">Likely range (MW)</th>
            <th className="py-2 pr-4 font-bold">Published</th>
            <th className="py-2 pr-4 text-right font-bold">Forecast age (h)</th>
            {revealed && <th className="py-2 pr-4 text-right font-bold">Actual (MW)</th>}
            {revealed && <th className="py-2 text-right font-bold">Error (MW)</th>}
          </tr>
        </thead>
        <tbody>
          {points.map((p) => (
            <tr key={p.start_time} className="border-b border-neutral-200">
              <td className="py-2 pr-4">{formatTime(p.start_time, tz)}</td>
              <td className="py-2 pr-4 text-right">{formatMW(p.forecast_mw)}</td>
              <td className="py-2 pr-4 text-right text-neutral-600">
                {p.range_low_mw == null
                  ? '-'
                  : `${formatMW(p.range_low_mw)} to ${formatMW(p.range_high_mw)}`}
              </td>
              <td className="py-2 pr-4">{formatDateTime(p.publish_time, tz)}</td>
              <td className="py-2 pr-4 text-right">{formatHours(p.horizon_hours)}</td>
              {revealed && <td className="py-2 pr-4 text-right">{formatMW(p.actual_mw)}</td>}
              {revealed && (
                <td className={`py-2 text-right ${errorClass(p.error_mw)}`}>
                  {formatMW(p.error_mw, { sign: true })}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
