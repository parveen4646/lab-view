// src/services/api.ts
import { MedicalData, HealthStatus, SystemStatus } from '../types/medical';

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

// ── ApiService class ──────────────────────────────────────────────────────────

class ApiService {
  private baseUrl: string;
  private token: string | null = null;

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl;
  }

  setToken(token: string | null): void {
    this.token = token;
  }

  /**
   * Core fetch wrapper.
   * - Attaches Authorization header when a token is set.
   * - Skips Content-Type for FormData (browser sets it with the multipart boundary).
   * - On non-2xx, parses the error body and throws with the backend's message.
   */
  private async makeRequest<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;

    const existingHeaders = (options.headers as Record<string, string>) ?? {};
    const headers: Record<string, string> = { ...existingHeaders };

    // Don't override Content-Type when the caller already set it,
    // and never set it for FormData bodies (browser owns that header).
    if (!(options.body instanceof FormData) && !headers['Content-Type']) {
      headers['Content-Type'] = 'application/json';
    }

    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }

    try {
      const response = await fetch(url, { ...options, headers });

      if (!response.ok) {
        let errorMessage = `HTTP error ${response.status}`;
        try {
          const errorData = await response.json();
          // Backend wraps HTTPException detail in { "error": "..." }
          // FastAPI 422 validation errors use { "detail": [...] }
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
  register,
  loginUser,
  getMe,
  getReports,
  getPercentiles,
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
