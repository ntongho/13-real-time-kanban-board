const COLUMN_NAMES = { todo: 'To Do', doing: 'In Progress', done: 'Done' };

function formatTime(value) {
  if (!value) return '';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
}

export default function ActivityFeed({ items = [] }) {
  return (
    <section className="activity-panel" aria-labelledby="activity-heading">
      <div className="activity-heading-row">
        <div><p className="app-eyebrow">BOARD HISTORY</p><h2 id="activity-heading">Recent activity</h2></div>
        <span className="activity-count">{items.length}</span>
      </div>
      {items.length ? (
        <ol className="activity-list">
          {items.slice(0, 8).map((item) => (
            <li key={item.id}>
              <span className="activity-marker" aria-hidden="true" />
              <span className="activity-message">{item.message || `${item.action || 'Updated'} ${item.card_title || 'a task'}`}</span>
              <time>{formatTime(item.created_at)}</time>
            </li>
          ))}
        </ol>
      ) : <p className="activity-empty">Task creation and movement will appear here.</p>}
      <p className="activity-legend">Columns: {Object.values(COLUMN_NAMES).join(' · ')}</p>
    </section>
  );
}
