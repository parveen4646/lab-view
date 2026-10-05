// src/services/api.ts
import { MedicalData, HealthStatus, SystemStatus } from '../types/medical';
import { authClient } from '@/lib/neon';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

// ── Response shape types ──────────────────────────────────────────────────────

interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface UserProfile {
  id: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
  is_verified: boolean;
}

export interface ReportSummary {
  id: string;
  filename: string;
  upload_at: string;
  extraction_quality: string | null;
  completeness_score: number | null;
  plausibility_score: number | null;
  tests_count: number;
}

export interface EnrichedResult {
  testName: string;
  value: number;
  percentile_rank?: number;
  interpretation?: string;
  z_score?: number;
  direction?: string;
}

export interface PercentileResponse {
  enriched: EnrichedResult[];
  overall_health_score: number | null;
  summary: string;
}

export interface QASource {
  source: string;
  corpus: string;
  relevance: number;
}

export interface QAResponse {
  answer: string;
  sources: QASource[];
  model_used: string;
}

// ── ApiService class ──────────────────────────────────────────────────────────

class ApiService {
  private baseUrl: string;
  private token: string | null = null;
  private tokenGetter: (() => Promise<string | null>) | null = null;

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl;
  }

  setToken(token: string | null): void {
    this.token = token;
  }

  setTokenGetter(getter: (() => Promise<string | null>) | null): void {
    this.tokenGetter = getter;
  }

  private async resolveToken(): Promise<string | null> {
    if (this.tokenGetter) return this.tokenGetter();
    return this.token;
  }

  // A 401 means the token is dead, but a hard redirect to /login alone
  // isn't enough: if this was a Neon Auth session, its cookie is still
  // valid, so Login's "already signed in -> bounce to /" effect would
  // immediately bounce straight back here, forming a login<->home loop.
  // Ending the Neon session first breaks that loop.
  private async forceSignOutAndRedirect(): Promise<void> {
    this.token = null;
    try {
      await authClient.signOut();
    } catch {
      // best-effort — still redirect even if sign-out itself fails
    }
    window.location.href = '/login';
  }

  private async makeRequest<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;

    const existingHeaders = (options.headers as Record<string, string>) ?? {};
    const headers: Record<string, string> = { ...existingHeaders };

    if (!(options.body instanceof FormData) && !headers['Content-Type']) {
      headers['Content-Type'] = 'application/json';
    }

    const token = await this.resolveToken();
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    try {
      const response = await fetch(url, { ...options, headers });

      if (!response.ok) {
        // On 401, try once more with a freshly fetched token before giving up.
        if (response.status === 401 && token && this.tokenGetter) {
          const freshToken = await this.tokenGetter();
          if (freshToken && freshToken !== token) {
            this.token = freshToken;
            const retryHeaders = { ...headers, Authorization: `Bearer ${freshToken}` };
            const retryResponse = await fetch(url, { ...options, headers: retryHeaders });
            if (retryResponse.ok) return retryResponse.json() as Promise<T>;
          }
          await this.forceSignOutAndRedirect();
        } else if (response.status === 401 && token) {
          await this.forceSignOutAndRedirect();
        }

        let errorMessage = `HTTP error ${response.status}`;
        try {
          const errorData = await response.json();
          errorMessage =
            errorData.error ||
            (typeof errorData.detail === 'string' ? errorData.detail : null) ||
            errorMessage;
        } catch {
          // JSON parse failed; use the generic message
        }
        throw new Error(errorMessage);
      }

      return response.json() as Promise<T>;
    } catch (error) {
      console.error(`API request failed: ${url}`, error);
      throw error;
    }
  }

  // ── Auth endpoints ──────────────────────────────────────────────────────────
  // These return flat JSON bodies (no {success, data} wrapper).

  async register(
    email: string,
    password: string,
    fullName?: string,
  ): Promise<{ access_token: string }> {
    const result = await this.makeRequest<TokenResponse>('/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password, full_name: fullName ?? null }),
    });
    return { access_token: result.access_token };
  }

  async loginUser(email: string, password: string): Promise<{ access_token: string }> {
    const result = await this.makeRequest<TokenResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
    return { access_token: result.access_token };
  }

  async loginWithGoogle(credential: string): Promise<{ access_token: string }> {
    const result = await this.makeRequest<TokenResponse>('/auth/google', {
      method: 'POST',
      body: JSON.stringify({ credential }),
    });
    return { access_token: result.access_token };
  }

  async getMe(): Promise<UserProfile> {
    return this.makeRequest<UserProfile>('/auth/me');
  }

  // ── Reports endpoint (wrapped: { success, data, total }) ────────────────────

  async getReports(): Promise<ReportSummary[]> {
    const result = await this.makeRequest<{ success: boolean; data: ReportSummary[]; total: number }>(
      '/api/reports/',
    );
    return result.data;
  }

  // GET /api/reports/{id} returns extra DB fields alongside formatted_data —
  // formatted_data is the exact MedicalData shape saved at upload time, so
  // that's the only part the dashboard needs.
  async getReport(id: string): Promise<MedicalData> {
    const result = await this.makeRequest<{ success: boolean; data: { formatted_data: MedicalData } }>(
      `/api/reports/${id}`,
    );
    return result.data.formatted_data;
  }

  // ── Analytics endpoint (flat response) ─────────────────────────────────────

  async getPercentiles(
    results: { testName: string; value: number }[],
  ): Promise<PercentileResponse> {
    return this.makeRequest<PercentileResponse>('/api/analytics/percentile', {
      method: 'POST',
      body: JSON.stringify({ results }),
    });
  }

  // ── PDF Upload (wrapped: { success, message, data }) ───────────────────────

  async uploadPDF(file: File): Promise<MedicalData> {
    const formData = new FormData();
    formData.append('file', file);

    const result = await this.makeRequest<{ success: boolean; message: string; data: MedicalData }>(
      '/api/upload',
      { method: 'POST', body: formData },
    );
    return result.data;
  }

  // ── Health and Status (kept for compatibility) ──────────────────────────────

  async getHealth(): Promise<HealthStatus> {
    return this.makeRequest<HealthStatus>('/health');
  }

  async getStatus(): Promise<SystemStatus> {
    const result = await this.makeRequest<{ success: boolean; status: SystemStatus }>('/api/status');
    return result.status;
  }

  // ── Text analysis ───────────────────────────────────────────────────────────

  async analyzeText(text: string, tables?: unknown[]): Promise<MedicalData> {
    const result = await this.makeRequest<{ success: boolean; data: MedicalData }>('/api/analyze', {
      method: 'POST',
      body: JSON.stringify({ text, tables: tables ?? [] }),
    });
    return result.data;
  }

  // ── Patient data ────────────────────────────────────────────────────────────

  async getPatientData(patientId: string): Promise<MedicalData> {
    const result = await this.makeRequest<{ success: boolean; data: MedicalData }>(
      `/api/patient/${patientId}`,
    );
    return result.data;
  }

  // ── Q&A (RAG-grounded chat) ─────────────────────────────────────────────────

  async askQuestion(question: string, reportId?: string): Promise<QAResponse> {
    return this.makeRequest<QAResponse>('/api/qa/ask', {
      method: 'POST',
      body: JSON.stringify({ question, report_id: reportId ?? null }),
    });
  }

  // ── Available models ────────────────────────────────────────────────────────

  async getAvailableModels(): Promise<{ current_model: string; available_models: string[] }> {
    const result = await this.makeRequest<{
      success: boolean;
      data: { current_model: string; available_models: string[] };
    }>('/api/models');
    return result.data;
  }

  // ── Utility methods ─────────────────────────────────────────────────────────

  async ping(): Promise<boolean> {
    try {
      await this.getHealth();
      return true;
    } catch {
      return false;
    }
  }

  async isOllamaAvailable(): Promise<boolean> {
    // Retained for backward compat — the new backend uses Claude, not Ollama.
    return false;
  }

  validateFile(file: File): { valid: boolean; error?: string } {
    const maxSize = 16 * 1024 * 1024; // 16 MB
    const allowedTypes = ['application/pdf'];

    if (!allowedTypes.includes(file.type)) {
      return { valid: false, error: 'Only PDF files are allowed' };
    }
    if (file.size > maxSize) {
      return { valid: false, error: 'File size must be less than 16 MB' };
    }
    return { valid: true };
  }

  handleApiError(error: unknown): string {
    if (error instanceof Error) return error.message;
    if (typeof error === 'string') return error;
    return 'An unexpected error occurred';
  }
}

// ── Singleton ─────────────────────────────────────────────────────────────────

export const apiService = new ApiService();

// Named convenience exports (same surface as before, plus new methods)
export const {
  setToken,
  setTokenGetter,
  register,
  loginUser,
  loginWithGoogle,
  getMe,
  getReports,
  getReport,
  getPercentiles,
  askQuestion,
  getHealth,
  getStatus,
  uploadPDF,
  analyzeText,
  getPatientData,
  getAvailableModels,
  ping,
  isOllamaAvailable,
  validateFile,
  handleApiError,
} = apiService;

export default apiService;
