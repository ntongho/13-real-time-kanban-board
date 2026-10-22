import { useCallback, useEffect, useState } from 'react';
import Board from './components/Board.jsx';
import ActivityFeed from './components/ActivityFeed.jsx';
import { api, API_BASE } from './api.js';
import { useRealtimeBoard } from './hooks/useRealtimeBoard.js';

export default function App() {
  const [board, setBoard] = useState(null);
  const [activity, setActivity] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');

  const refreshBoard = useCallback(async ({ initial = false } = {}) => {
    if (initial) setLoading(true);
    else setRefreshing(true);
    try {
      const [nextBoard, nextActivity] = await Promise.all([api.getBoard(), api.getActivity()]);
      setBoard(nextBoard);
      setActivity(nextActivity);
      setError('');
    } catch (failure) {
      setError(failure.message || 'Could not load the board.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { refreshBoard({ initial: true }); }, [refreshBoard]);

  // Stable callback prevents reconnecting the socket on every render.
  const handleRealtimeEvent = useCallback(() => {
    refreshBoard();
  }, [refreshBoard]);
  const connectionStatus = useRealtimeBoard(handleRealtimeEvent, API_BASE);

  async function handleCreate(title, description) {
    await api.createCard({ title, description });
    await refreshBoard();
  }

  async function handleMove(cardId, columnId, position) {
    await api.moveCard(cardId, columnId, position);
    await refreshBoard();
  }

  async function handleDelete(cardId) {
    await api.deleteCard(cardId);
    await refreshBoard();
  }

  return (
    <main className="app-shell">
      <header className="app-header">
        <a className="brand" href="#top" aria-label="Team Kanban home"><span className="brand-mark" aria-hidden="true">K</span><span>team<span className="brand-light">board</span></span></a>
        <div className="header-right"><span className={`connection-pill connection-${connectionStatus}`}><i />{connectionStatus === 'connected' ? 'Live sync on' : connectionStatus === 'reconnecting' ? 'Reconnecting…' : 'Connecting…'}</span><span className="demo-label">SHARED DEMO BOARD</span></div>
      </header>
      <section className="welcome" id="top">
        <div><p className="app-eyebrow">A CLEARER WAY TO WORK TOGETHER</p><h1>Small steps.<br /><em>Real progress.</em></h1><p className="welcome-copy">Move tasks forward together. Changes sync with everyone viewing this board.</p></div>
        <div className="welcome-art" aria-hidden="true"><span className="art-card art-card-one">Plan <b>→</b> Build</span><span className="art-card art-card-two">One team</span><span className="art-orbit">✳</span><span className="art-base" /></div>
      </section>
      {error && <div className="app-error" role="alert"><strong>Connection issue:</strong> {error} <button type="button" onClick={() => refreshBoard({ initial: !board })}>Try again</button></div>}
      {refreshing && <p className="refresh-status" role="status">Syncing the latest board…</p>}
      <Board board={board} loading={loading} error={error} onCreate={handleCreate} onMove={handleMove} onDelete={handleDelete} />
      <ActivityFeed items={activity} />
      <footer className="app-footer"><span>TEAM KANBAN</span><span>One board · Shared progress · Live updates</span></footer>
    </main>
  );
}
