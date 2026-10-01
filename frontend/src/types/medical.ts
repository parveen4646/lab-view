// src/types/medical.ts

export interface ReferenceRange {
  min: number;
  max: number;
}

export interface LabResult {
  id: string;
  testName: string;
  value: number;
  unit: string;
  referenceRange: ReferenceRange;
  status: 'normal' | 'high' | 'low' | 'critical';
  date: string;
  category: string;
}

export interface TrendData {
  date: string;
  value: number;
  testName: string;
  status: 'normal' | 'high' | 'low' | 'critical';
}

export interface PatientInfo {
  id: string;
  name: string;
  age?: number;
  gender?: string;
  dateOfBirth?: string;
  lastTestDate: string;
}

export interface TestCategory {
  id: string;
  name: string;
  description: string;
  color: string;
  tests: string[];
}

export interface ProcessingMetadata {
  filename?: string;
  extraction_metadata?: {
    page_count?: number;
    table_count?: number;
    text_length?: number;
    extraction_method?: string;
    error?: string;
  };
  processing_timestamp?: string;
  ollama_available?: boolean;
  evaluation?: {
    completeness_score: number;
    plausibility_score: number;
    overall_quality: 'high' | 'medium' | 'low' | 'failed';
    tests_extracted: number;
    tests_with_ranges: number;
    tests_with_status: number;
    patient_fields_present: number;
    warnings: string[];
  };
}

export interface MedicalData {
  patientInfo: PatientInfo;
  latestResults: LabResult[];
  testCategories: TestCategory[];
  trendData: Record<string, TrendData[]>;
  processing_metadata?: ProcessingMetadata;
}

export interface APIResponse<T = any> {
  success: boolean;
  message?: string;
  error?: string;
  data?: T;
  details?: string;
}

export interface HealthStatus {
  status: string;
  services: {
    pdf_extractor: string;
    ollama: string;
    file_handler: string;
  };
  timestamp: string;
}

export interface SystemStatus {
  pdf_extractor: string;
  ollama: string;
  ollama_model: string;
  upload_folder: string;
  max_file_size: string;
}

// Upload-related types
export interface UploadProgress {
  loaded: number;
  total: number;
  percentage: number;
}

export interface FileValidation {
  valid: boolean;
  error?: string;
}

// Chart data types for visualization
export interface ChartDataPoint {
  date: string;
  value: number;
  status: 'normal' | 'high' | 'low' | 'critical';
  testName?: string;
}

export interface CategoryChartData {
  category: string;
  data: ChartDataPoint[];
  color: string;
}

// Filter and search types
export interface TestFilter {
  categories: string[];
  statuses: string[];
  dateRange: {
    start?: string;
    end?: string;
  };
  searchTerm?: string;
}

export interface SortConfig {
  key: keyof LabResult;
  direction: 'asc' | 'desc';
}

// Component prop types
export interface PatientCardProps {
  patient: PatientInfo;
  onPatientClick?: (patientId: string) => void;
  className?: string;
}

export interface LabResultCardProps {
  result: LabResult;
  showTrend?: boolean;
  trendData?: TrendData[];
  className?: string;
}

export interface CategoryFilterProps {
  categories: TestCategory[];
  selectedCategories: string[];
  onCategoryChange: (categories: string[]) => void;
}

export interface TrendChartProps {
  data: TrendData[];
  testName: string;
  height?: number;
  showGrid?: boolean;
  showTooltip?: boolean;
}

// Hook return types
export interface UseMedicalDataReturn {
  data: MedicalData | null;
  loading: boolean;
  error: string | null;
  uploadPDF: (file: File) => Promise<void>;
  analyzeText: (text: string) => Promise<void>;
  retry: () => void;
  clearError: () => void;
}

export interface UseApiStatusReturn {
  isOnline: boolean;
  isOllamaAvailable: boolean;
  systemStatus: SystemStatus | null;
  lastChecked: Date | null;
  checkStatus: () => Promise<void>;
}

// Error types
export interface ApiError extends Error {
  status?: number;
  details?: string;
}

export class ValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ValidationError';
  }
}

export class NetworkError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'NetworkError';
  }
}

export class ProcessingError extends Error {
  constructor(message: string, public details?: string) {
    super(message);
    this.name = 'ProcessingError';
  }
}

// Form types
export interface TextAnalysisForm {
  text: string;
  tables?: TableData[];
}

export interface TableData {
  id: string;
  headers: string[];
  rows: string[][];
  page?: number;
}

// Configuration types
export interface ApiConfig {
  baseUrl: string;
  timeout: number;
  retryAttempts: number;
  retryDelay: number;
}

export interface AppConfig {
  api: ApiConfig;
  ui: {
    theme: 'light' | 'dark' | 'auto';
    chartsEnabled: boolean;
    trendsEnabled: boolean;
    maxFileSize: number;
    allowedFileTypes: string[];
  };
  features: {
    ollamaIntegration: boolean;
    batchProcessing: boolean;
    exportEnabled: boolean;
    printEnabled: boolean;
  };
}

// Constants
export const TEST_STATUSES = ['normal', 'high', 'low', 'critical'] as const;
export const TEST_CATEGORIES = ['blood', 'lipid', 'liver', 'kidney', 'metabolic'] as const;
export const CHART_COLORS = {
  primary: 'hsl(var(--chart-primary))',
  secondary: 'hsl(var(--chart-secondary))',
  tertiary: 'hsl(var(--chart-tertiary))',
  quaternary: 'hsl(var(--chart-quaternary))',
  normal: 'hsl(142, 76%, 36%)',
  high: 'hsl(0, 84%, 60%)',
  low: 'hsl(45, 93%, 47%)',
  critical: 'hsl(0, 72%, 51%)'
} as const;

// Utility types
export type TestStatus = typeof TEST_STATUSES[number];
export type TestCategoryId = typeof TEST_CATEGORIES[number];
export type ChartColor = keyof typeof CHART_COLORS;