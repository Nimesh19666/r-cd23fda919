// Formatting helpers. Dates stay as 'YYYY-MM-DD' strings so the browser's own
// timezone can never shift a delivery day. Times are shown in the market timezone.

const timeFormatters = new Map()
const dateTimeFormatters = new Map()

function timeFormatter(tz) {
  if (!timeFormatters.has(tz)) {
    timeFormatters.set(
      tz,
      new Intl.DateTimeFormat('en-GB', {
        timeZone: tz,
        hour: '2-digit',
        minute: '2-digit',
        hourCycle: 'h23',
      }),
    )
  }
  return timeFormatters.get(tz)
}

function dateTimeFormatter(tz) {
  if (!dateTimeFormatters.has(tz)) {
    dateTimeFormatters.set(
      tz,
      new Intl.DateTimeFormat('en-GB', {
        timeZone: tz,
        day: 'numeric',
        month: 'short',
        hour: '2-digit',
        minute: '2-digit',
        hourCycle: 'h23',
      }),
    )
  }
  return dateTimeFormatters.get(tz)
}

// value: epoch milliseconds or an ISO string
export function formatTime(value, tz) {
  return timeFormatter(tz).format(new Date(value))
}

export function formatDateTime(value, tz) {
  return dateTimeFormatter(tz).format(new Date(value))
}

export function formatMW(value, { sign = false } = {}) {
  if (value === null || value === undefined) return '-'
  const rounded = Math.round(value)
  const digits = Math.abs(rounded).toLocaleString('en-GB')
  if (rounded < 0) return `-${digits}`
  return sign && rounded > 0 ? `+${digits}` : digits
}

export function formatHours(value) {
  return value === null || value === undefined ? '-' : value.toFixed(1)
}

// Add days to a 'YYYY-MM-DD' string without involving the local timezone.
export function addDays(isoDate, days) {
  const [year, month, day] = isoDate.split('-').map(Number)
  return new Date(Date.UTC(year, month - 1, day + days)).toISOString().slice(0, 10)
}

export function clampDate(value, first, last) {
  if (value < first) return first
  if (value > last) return last
  return value
}

// 'Thursday 15 January' from a 'YYYY-MM-DD' string, without involving the local timezone.
export function formatDay(isoDate) {
  const [year, month, day] = isoDate.split('-').map(Number)
  return new Intl.DateTimeFormat('en-GB', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    timeZone: 'UTC',
  }).format(new Date(Date.UTC(year, month - 1, day)))
}
