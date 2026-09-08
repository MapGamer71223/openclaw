/**
 * Central API client for the JanSatark AI backend.
 *
 * This is the ONLY place that knows about base URLs, fetch(), headers,
 * timeouts, and error shapes. Every other service file should import
 * `apiGet` / `apiPost` / `apiUpload` from here instead of calling fetch
 * directly.
 *
 * ---------------------------------------------------------------------
 * CONFIGURING THE BACKEND URL
 * ---------------------------------------------------------------------
 * Set EXPO_PUBLIC_API_BASE_URL in a `.env` file at the project root
 * (artifacts/verisight-ai/.env). Expo inlines any EXPO_PUBLIC_* variable
 * into the JS bundle at build time, so this works in dev and in
 * production builds alike. See `.env.example` next to this file.
 *
 * IMPORTANT (why this matters on a phone / emulator, not just a browser):
 *   - iOS Simulator: the simulator shares the Mac's network stack, so
 *     `http://localhost:8000` reaches a backend running on your machine.
 *   - Android Emulator: the emulator has its own virtual network. It
 *     cannot see "localhost" as your machine -- use the emulator's
 *     special alias `http://10.0.2.2:8000` instead.
 *   - Physical phone (Expo Go / dev build): "localhost" means the phone
 *     itself. You need your computer's LAN IP, e.g.
 *     `http://192.168.1.23:8000`, and the phone + computer must be on
 *     the same Wi-Fi network.
 *   - Production: point EXPO_PUBLIC_API_BASE_URL at your deployed
 *     backend, e.g. `https://api.jansatark.example.com`.
 *
 * If EXPO_PUBLIC_API_BASE_URL is not set, this file falls back to a
 * best-effort guess (see `guessDevBaseUrl` below) so local development
 * "just works" most of the time on a physical device on the same
 * network as your dev machine, but you should still set the env var
 * explicitly for anything beyond quick local testing.
 */
import Constants from 'expo-constants';
import { uploadAsync, FileSystemUploadType } from 'expo-file-system/legacy';
import { Platform } from 'react-native';

const DEFAULT_BACKEND_PORT = 8000;

/**
 * Best-effort guess at a reachable backend URL when no explicit
 * EXPO_PUBLIC_API_BASE_URL is configured. Uses the Metro/Expo dev
 * server's host (which Expo already knows how to reach from a device,
 * simulator, or emulator) and swaps in the backend's port.
 */
function guessDevBaseUrl(): string {
  // `hostUri` looks like "172.16.178.241:8081" (LAN) or "localhost:8081"
  const hostUri =
    Constants.expoConfig?.hostUri ??
    (Constants as any)?.manifest2?.extra?.expoClient?.hostUri ??
    (Constants as any)?.manifest?.hostUri;

  let host = typeof hostUri === 'string' && hostUri.length > 0 ? hostUri.split(':')[0] : 'localhost';

  // 0.0.0.0 is a server bind address, never a valid HTTP client destination.
  if (host === '0.0.0.0') {
    host = Platform.OS === 'android' ? '10.0.2.2' : 'localhost';
  }

  // Android emulator can't resolve "localhost"
  if (Platform.OS === 'android' && (host === 'localhost' || host === '127.0.0.1')) {
    return `http://10.0.2.2:${DEFAULT_BACKEND_PORT}`;
  }

  return `http://${host}:${DEFAULT_BACKEND_PORT}`;
}

function resolveBaseUrl(): string {
  const configured = process.env.EXPO_PUBLIC_API_BASE_URL;
  if (configured && configured.trim().length > 0) {
    let url = configured.trim().replace(/\/+$/, '');
    
    // Replace invalid 0.0.0.0 with reachable host
    if (url.includes('0.0.0.0')) {
      const hostUri = Constants.expoConfig?.hostUri;
      const lanHost = typeof hostUri === 'string' ? hostUri.split(':')[0] : null;
      const replacement = lanHost && lanHost !== '0.0.0.0' ? lanHost : (Platform.OS === 'android' ? '10.0.2.2' : 'localhost');
      url = url.replace(/0\.0\.0\.0/g, replacement);
    }

    if (Platform.OS === 'android' && (url.includes('localhost') || url.includes('127.0.0.1'))) {
      url = url.replace(/localhost/g, '10.0.2.2').replace(/127\.0\.0\.1/g, '10.0.2.2');
    }
    return url;
  }
  return guessDevBaseUrl();
}

export const API_BASE_URL = resolveBaseUrl();

/** Default request timeout, in milliseconds. */
const DEFAULT_TIMEOUT_MS = 20000;
/** Uploads and long-running demo seeding get more time. */
const UPLOAD_TIMEOUT_MS = 120000;

export class ApiError extends Error {
  status: number | null;
  body: unknown;
  isNetworkError: boolean;
  isTimeout: boolean;

  constructor(message: string, opts: { status?: number | null; body?: unknown; isNetworkError?: boolean; isTimeout?: boolean } = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = opts.status ?? null;
    this.body = opts.body ?? null;
    this.isNetworkError = opts.isNetworkError ?? false;
    this.isTimeout = opts.isTimeout ?? false;
  }
}

async function withTimeout<T>(promise: Promise<T>, ms: number, controller: AbortController): Promise<T> {
  const timeout = new Promise<never>((_, reject) => {
    setTimeout(() => {
      controller.abort();
      reject(new ApiError(`Request timed out after ${ms}ms`, { isTimeout: true }));
    }, ms);
  });
  return Promise.race([promise, timeout]);
}

async function parseBody(response: Response): Promise<unknown> {
  const contentType = response.headers.get('content-type') ?? '';
  if (contentType.includes('application/json')) {
    try {
      return await response.json();
    } catch {
      return null;
    }
  }
  try {
    return await response.text();
  } catch {
    return null;
  }
}

function extractErrorMessage(body: unknown, fallback: string): string {
  if (body && typeof body === 'object') {
    const detail = (body as any).detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail) && detail.length > 0) {
      // FastAPI validation errors: [{ loc, msg, type }, ...]
      return detail.map((d: any) => d?.msg).filter(Boolean).join('; ') || fallback;
    }
  }
  if (typeof body === 'string' && body.length > 0) return body;
  return fallback;
}

interface RequestOptions {
  timeoutMs?: number;
  signal?: AbortSignal;
}

async function request<T>(path: string, init: RequestInit, options: RequestOptions = {}): Promise<T> {
  const url = path.startsWith('http') ? path : `${API_BASE_URL}${path}`;
  const controller = new AbortController();

  // Let the caller cancel too (e.g. component unmount) alongside our own timeout.
  if (options.signal) {
    if (options.signal.aborted) controller.abort();
    else options.signal.addEventListener('abort', () => controller.abort());
  }

  let response: Response;
  try {
    response = await withTimeout(
      fetch(url, { ...init, signal: controller.signal }),
      options.timeoutMs ?? DEFAULT_TIMEOUT_MS,
      controller,
    );
  } catch (err) {
    if (err instanceof ApiError) throw err;
    const message = err instanceof Error ? err.message : 'Network request failed';
    throw new ApiError(
      `Could not reach the JanSatark AI backend at ${API_BASE_URL}. Check that it is running and that EXPO_PUBLIC_API_BASE_URL is reachable from this device. (${message})`,
      { isNetworkError: true },
    );
  }

  if (!response.ok) {
    const body = await parseBody(response);
    throw new ApiError(extractErrorMessage(body, `Request failed with status ${response.status}`), {
      status: response.status,
      body,
    });
  }

  if (response.status === 204) return undefined as T;
  const body = await parseBody(response);
  return body as T;
}

export function apiGet<T>(path: string, options?: RequestOptions): Promise<T> {
  return request<T>(path, { method: 'GET', headers: { Accept: 'application/json' } }, options);
}

export function apiPost<T>(path: string, body?: unknown, options?: RequestOptions): Promise<T> {
  return request<T>(
    path,
    {
      method: 'POST',
      headers: { Accept: 'application/json', ...(body ? { 'Content-Type': 'application/json' } : {}) },
      body: body ? JSON.stringify(body) : undefined,
    },
    options,
  );
}

export function apiDelete<T>(path: string, options?: RequestOptions): Promise<T> {
  return request<T>(path, { method: 'DELETE', headers: { Accept: 'application/json' } }, options);
}

export interface UploadFileInput {
  uri: string;
  name: string;
  mimeType: string;
}

/**
 * Uploads a file as multipart/form-data. React Native's fetch/FormData
 * implementation accepts `{ uri, name, type }` objects for file fields
 * (this is the standard Expo/React Native pattern -- it is NOT a real
 * `File`/`Blob`, but RN's networking layer knows how to stream it from
 * the given `uri`).
 */
export async function apiUpload<T>(path: string, file: UploadFileInput, fieldName = 'file', options?: RequestOptions): Promise<T> {
  const url = path.startsWith('http') ? path : `${API_BASE_URL}${path}`;

  if (Platform.OS !== 'web') {
    try {
      const response = await uploadAsync(url, file.uri, {
        httpMethod: 'POST',
        uploadType: FileSystemUploadType?.MULTIPART ?? 1,
        fieldName: fieldName,
        mimeType: file.mimeType || (file.name?.endsWith('.mp4') ? 'video/mp4' : 'image/jpeg'),
        headers: {
          Accept: 'application/json',
        },
      });

      if (response.status >= 200 && response.status < 300) {
        if (response.status === 204) return undefined as T;
        try {
          return JSON.parse(response.body) as T;
        } catch {
          return response.body as unknown as T;
        }
      } else {
        let errorMsg = `Request failed with status ${response.status}`;
        try {
          const body = JSON.parse(response.body);
          if (body?.detail) {
            errorMsg = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
          }
        } catch {}
        throw new ApiError(errorMsg, { status: response.status, body: response.body });
      }
    } catch (err: any) {
      if (err instanceof ApiError) throw err;
      const msg = err?.message || String(err);
      throw new ApiError(
        `Could not reach the JanSatark AI backend at ${API_BASE_URL}. Check that it is running and reachable from this device. (${msg})`,
        { isNetworkError: true },
      );
    }
  }

  // Web implementation using standard FormData / fetch
  const formData = new FormData();
  try {
    const res = await fetch(file.uri);
    const blob = await res.blob();
    const webFile = new File([blob], file.name || 'upload.jpg', { type: file.mimeType || 'image/jpeg' });
    formData.append(fieldName, webFile);
  } catch {
    formData.append(fieldName, {
      uri: file.uri,
      name: file.name || 'upload.jpg',
      type: file.mimeType || 'image/jpeg',
    } as any);
  }

  return request<T>(
    path,
    {
      method: 'POST',
      headers: { Accept: 'application/json' },
      body: formData,
    },
    { timeoutMs: UPLOAD_TIMEOUT_MS, ...options },
  );
}

/** Builds a fully-qualified URL for a backend-served asset (e.g. original media, ELA overlay). */
export function apiAssetUrl(path: string): string {
  return path.startsWith('http') ? path : `${API_BASE_URL}${path}`;
}
