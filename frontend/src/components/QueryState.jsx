export function Loading({ label = 'Loading...' }) {
  return (
    <p role="status" className="py-10 text-neutral-600">
      {label}
    </p>
  )
}

export function ErrorBox({ error }) {
  return (
    <div role="alert" className="border-l-4 border-brand bg-neutral-100 p-4">
      <p className="font-bold">Could not load data</p>
      <p className="mt-1 text-neutral-700">{error.message}</p>
    </div>
  )
}
