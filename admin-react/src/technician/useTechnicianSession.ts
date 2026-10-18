import { useCallback, useEffect, useRef } from 'react';
import { getSessionEpoch } from '../wecomSession';

export function useTechnicianSession() {
  const epoch = useRef(getSessionEpoch());
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);
  return useCallback(() => mounted.current && epoch.current === getSessionEpoch(), []);
}
