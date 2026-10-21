import { useEffect, useRef, useState } from 'react';

/**
 * Subscribe to the Kanban backend's WebSocket event stream.
 *
 * The backend broadcasts:
 *   { type: 'card.created' | 'card.moved', card: Card }
 *
 * onEvent(event) is called for each valid event. Keep board fetching/state
 * reconciliation in the app shell so this hook stays independent of UI.
 *
 * Set VITE_API_URL to the HTTP API base URL in Vite/hosting, for example
 * http://localhost:8000 locally or https://your-api.example.com in production.
 */
export function useRealtimeBoard(onEvent, apiBaseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000') {
  const [status, setStatus] = useState('connecting');
  const onEventRef = useRef(onEvent);

  useEffect(() => {
    onEventRef.current = onEvent;
  }, [onEvent]);

  useEffect(() => {
    let disposed = false;
    let socket;
    let retryTimer;
    let retryDelay = 500;

    const wsUrl = `${apiBaseUrl.replace(/^http/, 'ws').replace(/\/$/, '')}/ws`;

    function connect() {
      if (disposed) return;
      setStatus('connecting');
      socket = new WebSocket(wsUrl);

      socket.onopen = () => {
        retryDelay = 500;
        setStatus('connected');
      };

      socket.onmessage = (message) => {
        try {
          const event = JSON.parse(message.data);
          if (event && ['card.created', 'card.moved'].includes(event.type) && event.card) {
            onEventRef.current?.(event);
          }
        } catch (error) {
          // Ignore malformed messages; the next valid event can still be handled.
          console.warn('Ignoring invalid Kanban WebSocket message', error);
        }
      };

      socket.onerror = () => {
        // onclose performs the retry, avoiding duplicate timers.
        socket.close();
      };

      socket.onclose = () => {
        if (disposed) return;
        setStatus('reconnecting');
        retryTimer = window.setTimeout(connect, retryDelay);
        retryDelay = Math.min(retryDelay * 2, 8000);
      };
    }

    connect();
    return () => {
      disposed = true;
      window.clearTimeout(retryTimer);
      socket?.close();
    };
  }, [apiBaseUrl]);

  return status;
}
