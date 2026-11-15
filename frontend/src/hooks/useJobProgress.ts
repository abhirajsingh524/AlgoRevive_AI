import { useEffect, useRef, useState } from 'react';

export interface ProgressState {
  stage: string;
  progress: number;
  status: string;
  message: string;
  error?: string | null;
}

export function useJobProgress(
  jobId: string | null,
  onComplete?: (status: string) => void
) {
  const [progressState, setProgressState] = useState<ProgressState | null>(null);
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!jobId) {
      setProgressState(null);
      setIsConnected(false);
      return;
    }

    let isSubscribed = true;
    const token = localStorage.getItem('algorevive_token');
    const apiBase = import.meta.env.VITE_API_URL || 'http://localhost:8000';
    const wsProto = apiBase.startsWith('https') ? 'wss:' : 'ws:';
    const host = apiBase.replace(/^https?:\/\//, '');
    const wsUrl = `${wsProto}//${host}/api/v1/ws/jobs/${jobId}?token=${token || ''}`;

    try {
      const ws = new WebSocket(wsUrl);
      socketRef.current = ws;

      ws.onopen = () => {
        if (!isSubscribed) return;
        setIsConnected(true);
      };

      ws.onmessage = (event) => {
        if (!isSubscribed) return;
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'heartbeat') return;

          const update: ProgressState = {
            stage: data.stage || 'running',
            progress: typeof data.progress === 'number' ? data.progress : 0,
            status: data.status || 'running',
            message: data.message || `Stage: ${data.stage} (${data.progress}%)`,
            error: data.error || null,
          };
          setProgressState(update);

          if (
            data.status === 'generated' ||
            data.status === 'completed' ||
            data.status === 'failed'
          ) {
            if (onComplete) {
              onComplete(data.status);
            }
          }
        } catch (jsonErr) {
          console.warn('Failed to parse WebSocket progress payload:', jsonErr);
        }
      };

      ws.onerror = () => {
        if (isSubscribed) setIsConnected(false);
      };

      ws.onclose = () => {
        if (isSubscribed) setIsConnected(false);
      };
    } catch (wsErr) {
      console.warn('WebSocket init failed:', wsErr);
      if (isSubscribed) setIsConnected(false);
    }

    return () => {
      isSubscribed = false;
      if (socketRef.current) {
        socketRef.current.close();
        socketRef.current = null;
      }
    };
  }, [jobId]);

  return { progressState, isConnected };
}
