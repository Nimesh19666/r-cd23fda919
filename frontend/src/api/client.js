// The only place that calls fetch. Turns HTTP errors into readable Error messages.
export async function getJson(path) {
  const response = await fetch(path)
  if (!response.ok) {
    let message = response.statusText || 'Request failed'
    try {
      const body = await response.json()
      if (typeof body.detail === 'string') message = body.detail
      else if (Array.isArray(body.detail)) message = 'Invalid request'
    } catch {
      // The body was not JSON; keep the status text.
    }
    throw new Error(message)
  }
  return response.json()
}
