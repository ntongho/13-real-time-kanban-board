import { useEffect, useId, useRef, useState } from 'react';
import Card from './Card.jsx';
import CreateCardForm from './CreateCardForm.jsx';
import '../styles/board.css';

const DRAG_TYPE = 'application/x-kanban-card';

/**
 * MEMBER 3: a controlled view, not an API client or database.
 * Both dragging and selectors use onMove(cardId, columnId, position).
 * The parent supplies the saved board after success; props are never mutated.
 */
export default function Board({ board = null, loading = false, error = '', onCreate, onMove, onDelete }) {
  const headingId = useId();
  const draggedIdRef = useRef(null);
  const actionLock = useRef(false);
  const boardElementRef = useRef(null);
  const deletedIdRef = useRef(null);
  const [draggedId, setDraggedId] = useState(null);
  const [dropTarget, setDropTarget] = useState(null);
  const [pendingCardId, setPendingCardId] = useState(null);
  const [dragError, setDragError] = useState('');
  const [deletingCardId, setDeletingCardId] = useState(null);
  const columns = Array.isArray(board?.columns) ? board.columns : [];
  const taskCount = columns.reduce((total, column) => total + column.cards.length, 0);
  const errorText = typeof error === 'string' ? error : error?.message || '';
  const actionsBusy = pendingCardId !== null || deletingCardId !== null;
  const mutationsDisabled = loading || actionsBusy;
  const movesDisabled = mutationsDisabled || typeof onMove !== 'function';

  useEffect(() => {
    if (!deletedIdRef.current || columns.some((column) => column.cards.some((card) => card.id === deletedIdRef.current))) return;
    deletedIdRef.current = null;
    // Restore useful focus only if deleting removed the focused control.
    // Never steal focus from a control outside this board.
    if (document.activeElement === document.body || !document.activeElement?.isConnected) {
      const next = boardElementRef.current?.querySelector('input:not(:disabled), button:not(:disabled), select:not(:disabled)')
        || boardElementRef.current?.querySelector('h2');
      next?.focus();
    }
  }, [board, deletingCardId]);

  function clearDrag() {
    draggedIdRef.current = null;
    setDraggedId(null);
    setDropTarget(null);
  }

  // This is the shared movement path. One pending move/delete at a time avoids
  // duplicate submissions; the server/parent still owns actual saved state.
  async function requestMove(cardId, columnId, position) {
    if (loading || actionLock.current || typeof onMove !== 'function') return;
    const card = columns.flatMap((column) => column.cards).find((item) => item.id === cardId);
    const destination = columns.find((column) => column.id === columnId);
    if (!card || !destination) throw new Error('This task or column is no longer available. Refresh the board and try again.');
    if (card.column_id === columnId) return; // Same-column reordering is outside this MVP.
    const appendPosition = destination.cards.filter((item) => item.id !== cardId).length;

    actionLock.current = true;
    setPendingCardId(cardId);
    setDragError('');
    try {
      await onMove(cardId, columnId, position ?? appendPosition);
    } finally {
      actionLock.current = false;
      setPendingCardId(null);
    }
  }

  // Delete is available only when the app shell supplies the real API callback.
  async function requestDelete(cardId) {
    if (loading || actionLock.current || typeof onDelete !== 'function') throw new Error('Please wait for the current operation to finish.');
    const exists = columns.some((column) => column.cards.some((card) => card.id === cardId));
    if (!exists) throw new Error('This task is no longer available. Refresh the board and try again.');
    actionLock.current = true;
    clearDrag();
    setDragError('');
    setDeletingCardId(cardId);
    try {
      await onDelete(cardId);
      deletedIdRef.current = cardId;
    } finally {
      actionLock.current = false;
      setDeletingCardId(null);
    }
  }

  function startDrag(cardId, event) {
    if (movesDisabled || !event.dataTransfer) {
      event.preventDefault();
      return;
    }
    draggedIdRef.current = cardId;
    setDraggedId(cardId);
    setDragError('');
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData(DRAG_TYPE, cardId);
    event.dataTransfer.setData('text/plain', cardId); // Firefox/native drag support.
  }

  function dragOver(event, columnId) {
    const card = columns.flatMap((column) => column.cards).find((item) => item.id === draggedIdRef.current);
    if (movesDisabled || !card || card.column_id === columnId) {
      if (event.dataTransfer) event.dataTransfer.dropEffect = 'none';
      setDropTarget(null);
      return;
    }
    event.preventDefault(); // Enables dropping onto this column.
    if (event.dataTransfer) event.dataTransfer.dropEffect = 'move';
    setDropTarget(columnId);
  }

  function dragLeave(event, columnId) {
    // Crossing a child card inside this column is not leaving the drop zone.
    if (!event.currentTarget.contains(event.relatedTarget)) {
      setDropTarget((current) => current === columnId ? null : current);
    }
  }

  async function dropCard(event, columnId) {
    event.preventDefault();
    event.stopPropagation();
    const cardId = draggedIdRef.current;
    const payload = event.dataTransfer?.getData(DRAG_TYPE);
    clearDrag();
    // Accept only a drag begun by this Board, not arbitrary text/files/UUIDs.
    if (!cardId || payload !== cardId || movesDisabled) return;
    try {
      await requestMove(cardId, columnId);
    } catch (failure) {
      setDragError(typeof failure === 'string' ? failure : failure?.message || 'Could not move this task. Please try again.');
    }
  }

  return (
    <section ref={boardElementRef} className="kb-board" aria-labelledby={headingId} aria-busy={loading} onKeyDown={(event) => { if (event.key === 'Escape') clearDrag(); }}>
      <header className="kb-board-header">
        <div>
          <p className="kb-eyebrow">TEAM WORKSPACE</p>
          <h2 id={headingId} tabIndex={-1}>{board?.title || 'Demo Board'}</h2>
          <p className="kb-board-description">A shared place for your next move.</p>
        </div>
        {board && <span className="kb-task-total">{taskCount} {taskCount === 1 ? 'task' : 'tasks'}</span>}
      </header>

      {errorText && <div className="kb-error" role="alert"><strong>Something went wrong.</strong> {errorText}</div>}
      {dragError && <div className="kb-error" role="alert">{dragError}</div>}
      {loading && <p className="kb-loading-message" role="status">{board ? 'Updating board…' : 'Loading board…'}</p>}

      {!board && loading && (
        <div className="kb-columns kb-skeleton-columns" aria-hidden="true">
          {[0, 1, 2].map((number) => <div className="kb-skeleton-column" key={number}><span /><div /><div /></div>)}
        </div>
      )}

      {!board && !loading && (
        <div className="kb-unavailable">
          <span className="kb-unavailable-icon" aria-hidden="true">▦</span>
          <h3>{errorText ? 'We couldn’t load this board' : 'Your board will appear here'}</h3>
          <p>{errorText ? 'Please try again when the connection is available.' : 'Provide board data to display its columns and tasks.'}</p>
        </div>
      )}

      {board && (
        <>
          <CreateCardForm onCreate={onCreate} disabled={mutationsDisabled} />
          <div className="kb-board-toolbar">
            <p>YOUR WORK, AT A GLANCE</p>
            <span role={draggedId ? 'status' : undefined}>{draggedId ? 'Drop in a highlighted column to move this task.' : 'Drag a task to another column, or use “Move to”'}</span>
          </div>
          <div className="kb-columns">
            {columns.map((column) => (
              <section
                className={`kb-column${dropTarget === column.id ? ' kb-column--drop-target' : ''}`}
                data-column={column.id}
                key={column.id}
                aria-label={`${column.title} column`}
                onDragOver={(event) => dragOver(event, column.id)}
                onDragLeave={(event) => dragLeave(event, column.id)}
                onDrop={(event) => dropCard(event, column.id)}
              >
                <header className="kb-column-header">
                  <span className="kb-column-dot" aria-hidden="true" />
                  <h3>{column.title}</h3>
                  <span className="kb-column-count" aria-label={`${column.cards.length} ${column.cards.length === 1 ? 'task' : 'tasks'}`}>{column.cards.length}</span>
                </header>
                <div className="kb-card-list">
                  {[...column.cards].sort((a, b) => a.position - b.position).map((card) => (
                    <Card
                      key={card.id} card={card} columns={columns}
                      onMove={typeof onMove === 'function' ? requestMove : undefined}
                      onDelete={typeof onDelete === 'function' ? requestDelete : undefined}
                      disabled={mutationsDisabled} pending={pendingCardId === card.id} deleting={deletingCardId === card.id}
                      dragging={draggedId === card.id} onDragStart={startDrag} onDragEnd={clearDrag}
                    />
                  ))}
                  {column.cards.length === 0 && (
                    <div className="kb-empty-column">
                      <span aria-hidden="true">＋</span>
                      <p>No tasks in {column.title} yet.</p>
                      <small>Create a task or drag one here.</small>
                    </div>
                  )}
                </div>
              </section>
            ))}
          </div>
          <footer className="kb-board-footer"><span className="kb-footer-dot" /> Small steps. Clear progress.</footer>
        </>
      )}
    </section>
  );
}
