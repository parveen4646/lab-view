import { useEffect, useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { useAuth } from '@/contexts/AuthContext';
import { apiService } from '@/services/api';
import { FileText, Upload, ArrowLeft, Trash2, TrendingUp } from 'lucide-react';

interface ReportSummary {
  id: string;
  filename: string;
  upload_at: string;
  extraction_quality: string | null;
  completeness_score: number | null;
  plausibility_score: number | null;
  tests_count: number;
}

const qualityColor = (q: string | null) => {
  if (q === 'high') return 'bg-green-100 text-green-800 border-green-200';
  if (q === 'medium') return 'bg-yellow-100 text-yellow-800 border-yellow-200';
  if (q === 'low') return 'bg-orange-100 text-orange-800 border-orange-200';
  return 'bg-gray-100 text-gray-600 border-gray-200';
};

const Reports = () => {
  const { user, token, isLoading: authLoading } = useAuth();
  const navigate = useNavigate();
  const [reports, setReports] = useState<ReportSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (authLoading) return;
    if (!user) {
      navigate('/login');
      return;
    }
    apiService
      .getReports()
      .then((data) => setReports(data))
      .catch((e) => setError(e.message ?? 'Failed to load reports'))
      .finally(() => setLoading(false));
  }, [user, authLoading, navigate]);

  const handleDelete = async (id: string) => {
    try {
      await fetch(`${import.meta.env.VITE_API_URL ?? 'http://localhost:8000'}/api/reports/${id}`, {
        method: 'DELETE',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      setReports((prev) => prev.filter((r) => r.id !== id));
    } catch {
      // non-fatal
    }
  };

  return (
    <div className="min-h-screen bg-background">
      {/* Nav */}
      <div className="border-b bg-background/95 backdrop-blur">
        <div className="max-w-5xl mx-auto px-4 md:px-6 py-3 flex items-center justify-between gap-3">
          <Link to="/" className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors">
            <ArrowLeft className="h-4 w-4" />
            Dashboard
          </Link>
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground hidden sm:inline">
              {user?.full_name ?? user?.email}
            </span>
            <Button size="sm" variant="outline" className="h-8 text-xs gap-1.5" onClick={() => navigate('/upload')}>
              <Upload className="h-3.5 w-3.5" />
              Upload
            </Button>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="max-w-5xl mx-auto px-4 md:px-6 py-8">
        <div className="mb-6">
          <h1 className="text-2xl font-semibold text-foreground">Report History</h1>
          <p className="text-sm text-muted-foreground mt-1">All lab reports uploaded to your account</p>
        </div>

        {loading && (
          <div className="text-center py-16 text-muted-foreground text-sm">Loading reports…</div>
        )}

        {error && (
          <Card className="border-red-200 bg-red-50">
            <CardContent className="py-6 text-center text-red-600 text-sm">{error}</CardContent>
          </Card>
        )}

        {!loading && !error && reports.length === 0 && (
          <Card>
            <CardContent className="py-16 text-center">
              <FileText className="h-10 w-10 text-muted-foreground mx-auto mb-4" />
              <p className="text-sm font-medium text-foreground mb-1">No reports yet</p>
              <p className="text-xs text-muted-foreground mb-6">Upload your first lab report to get started</p>
              <Button size="sm" onClick={() => navigate('/upload')} className="gap-1.5">
                <Upload className="h-4 w-4" />
                Upload Report
              </Button>
            </CardContent>
          </Card>
        )}

        {!loading && reports.length > 0 && (
          <div className="space-y-3">
            {reports.map((r) => (
              <Card key={r.id} className="hover:shadow-sm transition-shadow">
                <CardContent className="py-4 px-5 flex items-center justify-between gap-4 flex-wrap">
                  <div className="flex items-start gap-3 min-w-0">
                    <FileText className="h-5 w-5 text-muted-foreground mt-0.5 shrink-0" />
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-foreground truncate">{r.filename}</p>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        {new Date(r.upload_at).toLocaleDateString('en-US', {
                          year: 'numeric', month: 'short', day: 'numeric',
                          hour: '2-digit', minute: '2-digit',
                        })}
                        {' · '}
                        {r.tests_count} test{r.tests_count !== 1 ? 's' : ''}
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    {r.extraction_quality && (
                      <Badge variant="outline" className={`text-[10px] h-5 px-2 ${qualityColor(r.extraction_quality)}`}>
                        {r.extraction_quality}
                      </Badge>
                    )}
                    {r.completeness_score !== null && (
                      <div className="flex items-center gap-1 text-xs text-muted-foreground">
                        <TrendingUp className="h-3.5 w-3.5" />
                        {Math.round((r.completeness_score ?? 0) * 100)}%
                      </div>
                    )}
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 w-7 p-0 text-muted-foreground hover:text-red-500"
                      onClick={() => handleDelete(r.id)}
                      title="Delete report"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default Reports;
