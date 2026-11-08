import axios from 'axios';
import type {errorResponse} from './types/types';

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000',
});

export function errorMessage(error: unknown): string {
  if (axios.isAxiosError<errorResponse>(error)) {
    return error.response?.data?.error?.message || 'Could not reach the backend. Check that it is running.';
  }
  return 'The request could not be completed. Please try again.';
}

export function apiUrl(relativePath: string): string {
  return new URL(relativePath, api.defaults.baseURL).toString();
}
