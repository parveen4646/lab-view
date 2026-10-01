import { useState, useRef, useEffect, DragEvent } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Upload as UploadIcon, FileText, AlertTriangle, Stethoscope, LogIn } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { useAuth } from '@/contexts/AuthContext';
import { apiService } from '@/services/api';

const Upload = () => {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isBackendDown, setIsBackendDown] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const { toast } = useToast();
  const { user } = useAuth();

  // Ping backend on mount to show connectivity warning early
  useEffect(() => {
    apiService.ping().then((ok) => setIsBackendDown(!ok));
  }, []);

  const handleFileSelect = (file: File) => {
    const validation = apiService.validateFile(file);
    if (!validation.valid) {
      toast({
        title: 'Invalid File',
        description: validation.error,
        variant: 'destructive',
      });
      return;
    }
    setSelectedFile(file);
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFileSelect(file);
  };

  const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleFileSelect(file);
  };

  const handleAnalyze = async () => {
    if (!selectedFile) return;
    setIsLoading(true);
    try {
      const reportData = await apiService.uploadPDF(selectedFile);
      const tests = reportData.processing_metadata?.evaluation?.tests_extracted ?? 0;
      if (tests === 0) {
        toast({
          title: 'No Results Extracted',
          description:
            "We processed the PDF but couldn't extract any lab values from it. " +
            'This can happen with scanned/image PDFs or unusual report layouts.',
          variant: 'destructive',
        });
      } else if (reportData.processing_metadata?.input_truncated) {
        toast({
          title: 'Report Partially Processed',
          description:
            'This report was long enough that only part of it could be analyzed on the ' +
            'free tier — some results further into the document may be missing.',
        });
      }
      navigate('/dashboard', { state: { reportData } });
    } catch (error) {
      toast({
        title: 'Analysis Failed',
        description: apiService.handleApiError(error),
        variant: 'destructive',
      });
      // Re-check backend status after a failure
      apiService.ping().then((ok) => setIsBackendDown(!ok));
    } finally {
      setIsLoading(false);
    }
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className="min-h-screen bg-background p-4 md:p-8">
      <div className="max-w-2xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 bg-foreground rounded-full flex items-center justify-center">
              <Stethoscope className="w-5 h-5 text-background" />
            </div>
            <div>
              <h1 className="text-xl font-semibold text-foreground">MedLab</h1>
              <p className="text-xs text-muted-foreground">Lab Report Analysis</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Link to="/">
              <Button variant="outline" size="sm">View Dashboard</Button>
            </Link>
            {!user && (
              <Link to="/login">
                <Button variant="ghost" size="sm" className="gap-1">
                  <LogIn className="h-4 w-4" />
                  Sign In
                </Button>
              </Link>
            )}
          </div>
        </div>

        {/* Backend warning banner */}
        {isBackendDown && (
          <div className="flex items-start gap-3 p-4 rounded-lg border border-yellow-200 bg-yellow-50 text-yellow-800">
            <AlertTriangle className="h-5 w-5 mt-0.5 shrink-0" />
            <div className="text-sm">
              <p className="font-medium">Backend not connected</p>
              <p className="text-yellow-700 mt-0.5">
                The analysis service is unreachable at{' '}
                <code className="font-mono text-xs bg-yellow-100 px-1 rounded">
                  {import.meta.env.VITE_API_URL || 'http://localhost:8000'}
                </code>
                . Start the backend and try again.
              </p>
            </div>
          </div>
        )}

        {/* Login to save banner (shown when user is not authenticated) */}
        {!user && (
          <div className="flex items-center justify-between p-3 rounded-lg border bg-muted/50 text-sm text-muted-foreground">
            <span>Sign in to save your reports and track trends over time.</span>
            <Link to="/login">
              <Button variant="outline" size="sm">Sign In</Button>
            </Link>
          </div>
        )}

        {/* Upload card */}
        <Card className="shadow-sm">
          <CardHeader className="pb-4">
            <CardTitle className="text-lg font-medium">Upload Lab Report</CardTitle>
            <CardDescription>
              Drop your PDF lab report here. We'll extract and visualize your results using Claude AI.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Drop zone */}
            <div
              role="button"
              tabIndex={0}
              aria-label="Upload PDF file"
              className={`
                relative border-2 border-dashed rounded-xl p-10 text-center cursor-pointer
                transition-colors duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary
                ${isDragging
                  ? 'border-primary bg-primary/5'
                  : 'border-border hover:border-primary/50 hover:bg-muted/30'
                }
              `}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') fileInputRef.current?.click();
              }}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,application/pdf"
                className="hidden"
                onChange={handleInputChange}
              />
              <div className="flex flex-col items-center gap-3">
                <div className={`w-14 h-14 rounded-full flex items-center justify-center ${isDragging ? 'bg-primary/10' : 'bg-muted'}`}>
                  <UploadIcon className={`h-6 w-6 ${isDragging ? 'text-primary' : 'text-muted-foreground'}`} />
                </div>
                <div>
                  <p className="font-medium text-foreground">
                    {isDragging ? 'Drop your PDF here' : 'Drag & drop your PDF'}
                  </p>
                  <p className="text-sm text-muted-foreground mt-1">
                    or <span className="text-primary underline-offset-2 hover:underline">browse files</span>
                  </p>
                </div>
                <p className="text-xs text-muted-foreground">PDF only · max 16 MB</p>
              </div>
            </div>

            {/* Selected file info */}
            {selectedFile && (
              <div className="flex items-center gap-3 p-3 rounded-lg border bg-muted/30">
                <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
                  <FileText className="h-4 w-4 text-primary" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate text-foreground">{selectedFile.name}</p>
                  <p className="text-xs text-muted-foreground">{formatFileSize(selectedFile.size)}</p>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  className="shrink-0 text-muted-foreground hover:text-foreground"
                  onClick={(e) => {
                    e.stopPropagation();
                    setSelectedFile(null);
                    if (fileInputRef.current) fileInputRef.current.value = '';
                  }}
                >
                  Remove
                </Button>
              </div>
            )}

            {/* Analyze button */}
            <Button
              className="w-full h-12 bg-foreground hover:bg-foreground/90 text-background font-normal"
              disabled={!selectedFile || isLoading || isBackendDown}
              onClick={handleAnalyze}
            >
              {isLoading ? (
                <span className="flex items-center gap-2">
                  <span className="h-4 w-4 border-2 border-background/30 border-t-background rounded-full animate-spin" />
                  Analyzing report...
                </span>
              ) : (
                'Analyze Report'
              )}
            </Button>

            {isBackendDown && selectedFile && (
              <p className="text-xs text-center text-muted-foreground">
                Analysis is unavailable while the backend is offline.
              </p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default Upload;
