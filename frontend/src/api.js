const configuredBase = import.meta.env.VITE_API_URL?.trim();
export const API_BASE = (configuredBase || 'http://localhost:8000').replace(/\/$/, '');

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers: { ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...options.headers },
    });
  } catch {
    throw new Error('Could not reach the server. Check your connection and try again.');
  }
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      const message = body?.detail;
      detail = Array.isArray(message) ? message.map((item) => item.msg).join(', ') : (message || detail);
    } catch { /* retain generic HTTP message */ }
    throw new Error(detail);
  }
  if (response.status === 204) return null;
  return response.json();
}

export const api = {
  getBoard: () => request('/api/boards/demo'),
  getActivity: () => request('/api/boards/demo/activity'),
  createCard: ({ title, description }) => request('/api/boards/demo/cards', {
    method: 'POST', body: JSON.stringify({ title, description, column_id: 'todo' }),
  }),
  moveCard: (cardId, columnId, position) => request(`/api/cards/${encodeURIComponent(cardId)}/move`, {
    method: 'PATCH', body: JSON.stringify({ column_id: columnId, position }),
  }),
  deleteCard: (cardId) => request(`/api/cards/${encodeURIComponent(cardId)}`, { method: 'DELETE' }),
};
