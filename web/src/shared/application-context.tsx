import { createContext, useContext, useSyncExternalStore } from 'react';
import { getUiState, subscribeUiState } from './ui-state.mjs';

// The application owns feature services; views only consume data and actions.
export const ApplicationContext = createContext<any>(null);
export function useApplication() {
  const application = useContext(ApplicationContext);
  if (!application) throw new Error('Missing application session');
  return application;
}
export function useModel(model: any) {
  useSyncExternalStore(model.subscribe, model.snapshot);
  return model.data;
}
export function useUiFact(key: string, fallback: any = null) {
  return (useSyncExternalStore(subscribeUiState, getUiState) as Record<string, any>)[key] ?? fallback;
}
