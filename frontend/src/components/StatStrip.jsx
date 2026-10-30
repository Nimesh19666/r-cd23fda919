// A row of key numbers separated by thin rules.
const COLUMNS = { 2: 'lg:grid-cols-2', 3: 'lg:grid-cols-3', 4: 'lg:grid-cols-4' }

export default function StatStrip({ items }) {
  return (
    <dl
      className={`mt-8 grid gap-x-6 border-y-2 border-black sm:grid-cols-2 lg:gap-x-0 ${COLUMNS[items.length]}`}
    >
      {items.map(({ label, value, hint, tone }) => (
        <div
          key={label}
          className="py-4 lg:border-l lg:border-neutral-300 lg:px-5 lg:first:border-l-0 lg:first:pl-0"
        >
          <dt className="text-sm text-neutral-600">{label}</dt>
          <dd className="mt-1">
            <span
              className={`display block break-words text-2xl ${tone === 'brand' ? 'text-brand' : ''}`}
            >
              {value}
            </span>
            {hint && <span className="mt-1 block text-sm text-neutral-600">{hint}</span>}
          </dd>
        </div>
      ))}
    </dl>
  )
}
