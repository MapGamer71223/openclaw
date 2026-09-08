import AsyncStorage from '@react-native-async-storage/async-storage';
import React, { createContext, PropsWithChildren, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { Investigation } from '@/types/investigation';
import { getInvestigations } from '@/services/investigationService';
import { ApiError } from '@/services/api';

const HISTORY_CACHE_KEY = 'jansatark-history-cache';

interface InvestigationContextValue {
  investigations: Investigation[];
  current: Investigation | null;
  loading: boolean;
  /** Set when the last refresh failed (e.g. backend unreachable). Cached data, if any, is still shown. */
  error: string | null;
  setCurrent: (investigation: Investigation | null) => void;
  /** Optimistically adds/updates an investigation in the local list (e.g. right after upload) ahead of the next refresh. */
  addInvestigation: (investigation: Investigation) => void;
  /** Re-fetches the investigation list from the backend. */
  refresh: () => Promise<void>;
  /** Clears the on-device cache. Does not delete anything on the backend -- there is no delete-history endpoint. */
  clearHistory: () => Promise<void>;
}

const InvestigationContext = createContext<InvestigationContextValue | undefined>(undefined);

export function InvestigationProvider({ children }: PropsWithChildren) {
  const [investigations, setInvestigations] = useState<Investigation[]>([]);
  const [current, setCurrent] = useState<Investigation | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const mountedRef = useRef(true);

  const refresh = useCallback(async () => {
    try {
      const fresh = await getInvestigations();
      if (!mountedRef.current) return;
      setInvestigations(fresh);
      setError(null);
      AsyncStorage.setItem(HISTORY_CACHE_KEY, JSON.stringify(fresh)).catch(() => undefined);
    } catch (err) {
      if (!mountedRef.current) return;
      const message = err instanceof ApiError ? err.message : 'Could not load investigations from the backend.';
      setError(message);
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    // Paint instantly from cache, then reconcile with the backend.
    AsyncStorage.getItem(HISTORY_CACHE_KEY)
      .then((stored) => {
        if (stored && mountedRef.current) {
          try {
            setInvestigations(JSON.parse(stored) as Investigation[]);
          } catch {
            // ignore corrupt cache
          }
        }
      })
      .finally(() => refresh());
    return () => {
      mountedRef.current = false;
    };
  }, [refresh]);

  const addInvestigation = useCallback((investigation: Investigation) => {
    setInvestigations((items) => {
      const next = [investigation, ...items.filter((item) => item.id !== investigation.id)];
      AsyncStorage.setItem(HISTORY_CACHE_KEY, JSON.stringify(next)).catch(() => undefined);
      return next;
    });
  }, []);

  const clearHistory = useCallback(async () => {
    // NOTE: the backend has no "delete all investigations" endpoint, so this
    // only clears the on-device cache and the currently-viewed list. A
    // pull-to-refresh (or app restart) will reload the real history from
    // the backend, since it remains the source of truth.
    await AsyncStorage.removeItem(HISTORY_CACHE_KEY);
    setInvestigations([]);
    setCurrent(null);
  }, []);

  const value = useMemo(
    () => ({ investigations, current, loading, error, setCurrent, addInvestigation, refresh, clearHistory }),
    [investigations, current, loading, error, addInvestigation, refresh, clearHistory],
  );

  return <InvestigationContext.Provider value={value}>{children}</InvestigationContext.Provider>;
}

export function useInvestigations() {
  const context = useContext(InvestigationContext);
  if (!context) throw new Error('useInvestigations must be used within InvestigationProvider');
  return context;
}
