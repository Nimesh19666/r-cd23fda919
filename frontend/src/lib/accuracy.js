// Plain calculations for the accuracy page. No React in here.

// Below this share of average wind output, we call the forecast balanced rather than biased.
const LEAN_THRESHOLD = 0.03

export function leanOf(summary) {
  if (summary.bias_mw == null || !summary.mean_actual_mw) return 'unknown'
  const share = summary.bias_mw / summary.mean_actual_mw
  if (share > LEAN_THRESHOLD) return 'high'
  if (share < -LEAN_THRESHOLD) return 'low'
  return 'balanced'
}

export function dayCounts(byDay) {
  const days = byDay.filter((d) => d.n_compared > 0)
  return {
    total: days.length,
    tooHigh: days.filter((d) => d.bias_mw > 0).length,
  }
}
