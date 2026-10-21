import { useEffect, useId, useRef, useState } from 'react';

/**
 * MEMBER 3: card UI only. The optional onDelete callback is an extension,
 * not a claim that the team already has a delete API. Omit it to hide Delete.
 */
export default function Card({ card, columns, onMove, onDelete, disabled = false, pending = false, deleting = false, dragging = false, onDragStart, onDragEnd }) {
  const headingId = useId();
  const deleteButtonRef = useRef(null);
  const cancelButtonRef = useRef(null);
  const restoreFocusRef = useRef(false);
  const deleteLock = useRef(false);
  const [moving, setMoving] = useState(false);
  const [deletingHere, setDeletingHere] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState('');
  const hasDelete = typeof onDelete === 'function';
  const confirmOpen = confirming && hasDelete;
  const deleteBusy = deletingHere || deleting;
  const busy = moving || pending || deleteBusy;
  const currentColumn = columns.find((column) => column.id === card.column_id);
  const canDrag = !disabled && !busy && !confirmOpen && typeof onMove === 'function' && typeof onDragStart === 'function';

  useEffect(() => {
    if (!hasDelete) {
      if (confirming) setConfirming(false);
      return;
    }
    // This is inline confirmation, not a modal. Cancel gets the safe default focus.
    if (confirmOpen && !deleteBusy) cancelButtonRef.current?.focus();
    if (!confirmOpen && restoreFocusRef.current) {
      deleteButtonRef.current?.focus();
      restoreFocusRef.current = false;
    }
  }, [confirmOpen, deleteBusy, hasDelete, confirming]);

  async function handleMove(event) {
    const columnId = event.target.value;
    if (busy || disabled || confirmOpen || columnId === card.column_id || typeof onMove !== 'function') return;
    const destination = columns.find((column) => column.id === columnId);
    if (!destination) return;
    const position = destination.cards.filter((item) => item.id !== card.id).length;
    setMoving(true);
    setError('');
    try {
      await onMove(card.id, columnId, position);
    } catch (failure) {
      setError(typeof failure === 'string' ? failure : failure?.message || 'Could not move this task. Please try again.');
    } finally {
      setMoving(false);
    }
  }

  function beginDrag(event) {
    if (!canDrag || event.target.closest?.('select, input, textarea, button, a')) {
      event.preventDefault();
      return;
    }
    setError('');
    onDragStart(card.id, event);
  }

  function cancelDelete() {
    if (deleteBusy) return;
    restoreFocusRef.current = true;
    setConfirming(false);
    setError('');
  }

  async function confirmDelete() {
    if (!hasDelete || disabled || busy || deleteLock.current) return;
    deleteLock.current = true;
    setDeletingHere(true);
    setError('');
    try {
      await onDelete(card.id);
      // Only the parent removes the card from board props after success.
      restoreFocusRef.current = true;
      setConfirming(false);
    } catch (failure) {
      setError(typeof failure === 'string' ? failure : failure?.message || 'Could not delete this task. Please try again.');
    } finally {
      deleteLock.current = false;
      setDeletingHere(false);
    }
  }

  return (
    <article
      className={`kb-card${dragging ? ' kb-card--dragging' : ''}`}
      data-card-id={card.id} aria-labelledby={headingId} aria-busy={busy}
      draggable={canDrag} onDragStart={beginDrag} onDragEnd={onDragEnd}
      onKeyDown={(event) => { if (event.key === 'Escape' && confirmOpen && !deleteBusy) { event.preventDefault(); event.stopPropagation(); cancelDelete(); } }}
      title={canDrag ? 'Drag to another column, or use the Move to selector' : undefined}
    >
      <div className="kb-card-meta">
        <div className="kb-card-label">
          {typeof onDragStart === 'function' && <span className="kb-drag-grip" aria-hidden="true">⠿</span>}
          <span className="kb-card-reference">TASK · {card.id.slice(0, 6).toUpperCase()}</span>
        </div>
        <span className="kb-card-status" data-status={card.column_id}>{currentColumn?.title || card.column_id}</span>
      </div>
      <h4 id={headingId}>{card.title}</h4>
      {card.description && <p className="kb-card-description">{card.description}</p>}
      <div className="kb-card-actions">
        <label className="kb-move-label">
          <span>Move to</span>
          <select
            aria-label={`Move ${card.title} to`} value={card.column_id} onChange={handleMove}
            disabled={disabled || busy || confirmOpen || typeof onMove !== 'function'} draggable={false}
          >
            {columns.map((column) => <option value={column.id} key={column.id}>{column.title}</option>)}
          </select>
        </label>
      </div>
      {hasDelete && !confirmOpen && (
        <div className="kb-delete-row"><button ref={deleteButtonRef} className="kb-delete-button" type="button" aria-label={`Delete ${card.title}`} title="Delete task" disabled={disabled || busy} draggable={false} onClick={() => { setError(''); setConfirming(true); }}><svg viewBox="0 0 20 20" width="13" height="13" fill="none" aria-hidden="true"><path d="M3 5h14M7 5V3h6v2M5 5l1 12h8l1-12M8 8v6m4-6v6" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" /></svg>Delete</button></div>
      )}
      {confirmOpen && (
        <div className="kb-delete-confirmation" role="group" aria-labelledby={`${headingId}-delete-heading`}>
          <p id={`${headingId}-delete-heading`} className="kb-delete-heading">Delete this task?</p>
          <p className="kb-delete-description">Remove “{card.title}” from the board?</p>
          <div className="kb-delete-options">
            <button ref={cancelButtonRef} className="kb-delete-cancel" type="button" onClick={cancelDelete} disabled={deleteBusy}>Cancel</button>
            <button className="kb-delete-confirm" type="button" aria-label={`Confirm delete ${card.title}`} onClick={confirmDelete} disabled={disabled || busy}>{deleteBusy ? 'Deleting…' : 'Delete task'}</button>
          </div>
        </div>
      )}
      {busy && <p className="kb-card-feedback" role="status">{deleteBusy ? 'Deleting task…' : 'Moving task…'}</p>}
      {error && <p className="kb-field-error" role="alert">{error}</p>}
    </article>
  );
}
