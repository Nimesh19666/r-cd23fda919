import { useState } from 'react'
import { useMeta } from './api/queries'
import { ErrorBox, Loading } from './components/QueryState'
import { formatDateTime } from './lib/format'
import AccuracyPage from './pages/AccuracyPage'
import AssumptionsPage from './pages/AssumptionsPage'
import DecisionPage from './pages/DecisionPage'

const TABS = [
  { id: 'plan', label: 'Day-ahead plan' },
  { id: 'accuracy', label: 'Forecast accuracy' },
  { id: 'assumptions', label: 'Assumptions' },
]

function Page({ tab, meta }) {
  if (tab === 'accuracy') return <AccuracyPage />
  if (tab === 'assumptions') return <AssumptionsPage meta={meta} />
  return <DecisionPage meta={meta} />
}

export default function App() {
  const [tab, setTab] = useState('plan')
  const meta = useMeta()

  return (
    <div className="flex min-h-screen flex-col lg:flex-row">
      <aside className="flex flex-col bg-black px-6 py-8 text-white lg:sticky lg:top-0 lg:h-screen lg:w-80 lg:shrink-0">
        <div className="h-1 w-14 bg-brand" />
        <h1 className="mt-6 text-2xl font-bold">Day-ahead wind</h1>
        <p className="mt-1 text-sm text-neutral-400">GB wind forecast desk</p>

        <nav aria-label="Main" className="mt-8 flex flex-wrap gap-1 lg:flex-col">
          {TABS.map(({ id, label }) => (
            <button
              key={id}
              type="button"
              onClick={() => setTab(id)}
              aria-current={tab === id ? 'page' : undefined}
              className={
                tab === id
                  ? 'bg-brand px-4 py-3 text-left font-semibold text-white'
                  : 'px-4 py-3 text-left text-neutral-300 hover:text-white'
              }
            >
              {label}
            </button>
          ))}
        </nav>

        {meta.data && (
          <p className="mt-6 border-t border-neutral-800 pt-4 text-sm text-neutral-400 lg:mt-auto">
            Latest forecast on file:{' '}
            {formatDateTime(meta.data.forecasts_last_publish_time, meta.data.timezone)}
          </p>
        )}
      </aside>

      <main className="min-w-0 flex-1 px-5 py-8 lg:px-14 lg:py-12">
        {meta.isPending && <Loading />}
        {meta.isError && <ErrorBox error={meta.error} />}
        {meta.data && <Page tab={tab} meta={meta.data} />}
      </main>
    </div>
  )
}
