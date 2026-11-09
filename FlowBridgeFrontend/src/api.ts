import axios from 'axios';
import type {errorResponse} from './types/types';

export const REQUEST_TIMEOUT_MS = 90_000;

export const api = axios.create({
  timeout: REQUEST_TIMEOUT_MS,
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000',
});

export function errorMessage(error: unknown): string {
  if (axios.isAxiosError<errorResponse>(error)) {
    if (error.code === 'ECONNABORTED' || error.code === 'ETIMEDOUT') {
      return 'The request timed out. Try again, or import a smaller project.';
    }
    return error.response?.data?.error?.message || 'Could not reach the backend. Check that it is running.';
  }
  return 'The request could not be completed. Please try again.';
}

export function apiUrl(relativePath: string): string {
  return new URL(relativePath, api.defaults.baseURL).toString();
}
