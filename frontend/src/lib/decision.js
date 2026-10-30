// Plain calculations for the day-ahead plan screen. No React in here.

const mean = (values) => values.reduce((sum, v) => sum + v, 0) / values.length

// What the buyer could see at the cutoff.
export function planSummary(points) {
  if (points.length === 0) return null
  const published = points.map((p) => Date.parse(p.publish_time))
  const ahead = points.map((p) => p.horizon_hours)
  const floors = points.map((p) => p.range_low_mw).filter((v) => v != null)
  return {
    hours: points.length,
    forecastAverage: mean(points.map((p) => p.forecast_mw)),
    // The low end of the likely range, averaged over the day.
    countOnAtLeast: floors.length === points.length ? mean(floors) : null,
    latestPublished: Math.max(...published),
    versions: new Set(published).size,
    minAhead: Math.min(...ahead),
    maxAhead: Math.max(...ahead),
  }
}

// How the day turned out. Only used after the user reveals the outcome.
export function outcomeSummary(points) {
  const compared = points.filter((p) => p.actual_mw != null)
  if (compared.length === 0) return null
  const withFloor = compared.filter((p) => p.range_low_mw != null)
  return {
    hoursCompared: compared.length,
    actualAverage: mean(compared.map((p) => p.actual_mw)),
    forecastAverage: mean(compared.map((p) => p.forecast_mw)),
    floorHeld: withFloor.filter((p) => p.actual_mw >= p.range_low_mw).length,
    floorChecked: withFloor.length,
  }
}
