/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL?: string;
  readonly VITE_API_PREFIX?: string;
  readonly VITE_DATA_SOURCE?: string;
  readonly VITE_DECISION_COLORS?: string;
  readonly VITE_MOCK_RATE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
