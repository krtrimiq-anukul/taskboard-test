// Every call uses a relative /api path: the same address serves the page and the API.
async function call(path, options = {}) {
  const response = await fetch(`/api${path}`, { headers: { 'Content-Type': 'application/json' }, ...options });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      // not JSON: keep the status text
    }
    throw new Error(`${response.status}: ${detail}`);
  }
  return response.status === 204 ? null : response.json();
}

export const api = {
  info: () => call('/info'),
  tasks: () => call('/tasks'),
  create: (title) => call('/tasks', { method: 'POST', body: JSON.stringify({ title }) }),
  move: (id, status) => call(`/tasks/${id}`, { method: 'PATCH', body: JSON.stringify({ status }) }),
  remove: (id) => call(`/tasks/${id}`, { method: 'DELETE' }),
  exportTasks: () => call('/tasks/export', { method: 'POST' }),
};
