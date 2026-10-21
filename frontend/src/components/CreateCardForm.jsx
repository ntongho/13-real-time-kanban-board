import { useId, useRef, useState } from 'react';

/**
 * MEMBER 3: browser validation and form feedback only.
 * onCreate(title, description) is supplied by the preview or Member 5's shell.
 * A successful callback clears the fields; a rejected callback preserves them.
 */
export default function CreateCardForm({ onCreate, disabled = false }) {
  const formId = useId();
  const titleRef = useRef(null);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [titleError, setTitleError] = useState('');
  const [submitError, setSubmitError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const unavailable = disabled || submitting || typeof onCreate !== 'function';

  async function handleSubmit(event) {
    event.preventDefault();
    if (unavailable) return;
    const cleanTitle = title.trim();
    if (!cleanTitle) {
      setTitleError('Card title is required');
      setSubmitError('');
      titleRef.current?.focus();
      return;
    }
    setTitleError('');
    setSubmitError('');
    setSubmitting(true);
    try {
      await onCreate(cleanTitle, description.trim());
      setTitle('');
      setDescription('');
    } catch (failure) {
      setSubmitError(typeof failure === 'string' ? failure : failure?.message || 'Could not create this task. Please try again.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="kb-create-form" onSubmit={handleSubmit} noValidate aria-label="Create task">
      <div className="kb-form-heading"><span className="kb-form-icon" aria-hidden="true">＋</span><div><h3>Add a little momentum</h3><p>New tasks start in To Do.</p></div></div>
      <div className="kb-form-fields">
        <div className="kb-field kb-title-field">
          <label htmlFor={`${formId}-title`}>Task title <span aria-hidden="true">*</span></label>
          <input
            id={`${formId}-title`}
            ref={titleRef}
            value={title}
            onChange={(event) => { setTitle(event.target.value); if (event.target.value.trim()) setTitleError(''); setSubmitError(''); }}
            placeholder="What needs to get done?"
            maxLength={200}
            required
            aria-invalid={Boolean(titleError)}
            aria-describedby={titleError ? `${formId}-title-error` : undefined}
            disabled={unavailable}
          />
          {titleError && <p id={`${formId}-title-error`} className="kb-field-error" role="alert">{titleError}</p>}
        </div>
        <div className="kb-field kb-description-field">
          <label htmlFor={`${formId}-description`}>Description <span className="kb-optional">optional</span></label>
          <textarea
            id={`${formId}-description`}
            value={description}
            onChange={(event) => { setDescription(event.target.value); setSubmitError(''); }}
            placeholder="Add a little context…"
            rows={1}
            disabled={unavailable}
          />
        </div>
        <button className="kb-create-button" type="submit" disabled={unavailable}>
          <span aria-hidden="true">{submitting ? '◌' : '+'}</span> {submitting ? 'Adding task…' : 'Add task'}
        </button>
      </div>
      {submitting && <p className="kb-form-feedback" role="status">Waiting for the task to be created…</p>}
      {submitError && <p className="kb-submit-error" role="alert">{submitError}</p>}
    </form>
  );
}
