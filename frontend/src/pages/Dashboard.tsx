import { useEffect, useState } from 'react';
import { useLocation, useNavigate, Link } from 'react-router-dom';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { MedicalDashboard } from '@/components/medical/MedicalDashboard';
import { PatientCard } from '@/components/medical/PatientCard';
import { TestResultCard } from '@/components/medical/TestResultCard';
import { useAuth } from '@/contexts/AuthContext';
import { apiService, PercentileResponse } from '@/services/api';
import { MedicalData, LabResult } from '@/types/medical';
import { Activity, Upload, FileText, Stethoscope } from 'lucide-react';

// ── Health Score card ─────────────────────────────────────────────────────────

interface HealthScoreCardProps {
  score: number | null;
  summary: string;
}

function HealthScoreCard({ score, summary }: HealthScoreCardProps) {
  if (score === null) return null;

  const isGreen = score >= 75;
  const isYellow = score >= 50 && score < 75;
  const scoreColor = isGreen ? 'text-green-600' : isYellow ? 'text-yellow-500' : 'text-red-500';
  const borderBg = isGreen
    ? 'border-green-200 bg-green-50'
    : isYellow
    ? 'border-yellow-200 bg-yellow-50'
    : 'border-red-200 bg-red-50';

  return (
    <Card className={`border ${borderBg}`}>
      <CardContent className="flex items-center gap-6 pt-6 pb-6">
        <Activity className="h-8 w-8 text-muted-foreground shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
            Overall Health Score
          </p>
          <p className="text-sm text-muted-foreground mt-0.5">{summary}</p>
        </div>
        <span className={`text-5xl font-bold tabular-nums shrink-0 ${scoreColor}`}>
          {Math.round(score)}
        </span>
      </CardContent>
    </Card>
  );
}

// ── Real-data dashboard ───────────────────────────────────────────────────────

interface RealDataDashboardProps {
  reportData: MedicalData;
  percentiles: PercentileResponse | null;
}

function RealDataDashboard({ reportData, percentiles }: RealDataDashboardProps) {
  return (
    <div className="space-y-6">
      {percentiles && (
        <HealthScoreCard
          score={percentiles.overall_health_score}
          summary={percentiles.summary}
        />
      )}

      <PatientCard patient={reportData.patientInfo} />

      {reportData.latestResults.length > 0 ? (
        <div>
          <h2 className="text-base font-semibold text-foreground mb-4">Lab Results</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {reportData.latestResults.map((result: LabResult) => (
              <TestResultCard key={result.id} result={result} />
            ))}
          </div>
        </div>
      ) : (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground text-sm">
            No lab results were extracted from this report.
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// ── Navigation bar ────────────────────────────────────────────────────────────

interface NavBarProps {
  user: { full_name: string | null; email: string } | null;
}

function NavBar({ user }: NavBarProps) {
  const navigate = useNavigate();

  return (
    <div className="border-b bg-background/95 backdrop-blur">
      <div className="max-w-7xl mx-auto px-4 md:px-6 py-3 flex items-center justify-between gap-3">
        {/* Brand */}
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 bg-foreground rounded-full flex items-center justify-center shrink-0">
            <Stethoscope className="w-4 h-4 text-background" />
          </div>
          <div>
            <p className="text-sm font-semibold text-foreground leading-none">MedLab</p>
            {user && (
              <p className="text-xs text-muted-foreground mt-0.5 leading-none">
                {user.full_name ?? user.email}
              </p>
            )}
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2 flex-wrap justify-end">
          {user && (
            <Link to="/reports">
              <Button variant="outline" size="sm" className="gap-1.5 h-8 text-xs">
                <FileText className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">Report History</span>
                <span className="sm:hidden">History</span>
              </Button>
            </Link>
          )}
          <Button
            variant="outline"
            size="sm"
            className="gap-1.5 h-8 text-xs"
            onClick={() => navigate('/upload')}
          >
            <Upload className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Upload New Report</span>
            <span className="sm:hidden">Upload</span>
          </Button>
          {!user && (
            <Link to="/login">
              <Button
                size="sm"
                className="h-8 text-xs bg-foreground text-background hover:bg-foreground/90"
              >
                Sign In
              </Button>
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Dashboard page ────────────────────────────────────────────────────────────

interface LocationState {
  reportData?: MedicalData;
}

const Dashboard = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const { user } = useAuth();

  const locationState = location.state as LocationState | null;
  const reportData = locationState?.reportData ?? null;
  const isUsingMockData = reportData === null;

  const [percentiles, setPercentiles] = useState<PercentileResponse | null>(null);

  // Fetch percentile enrichment for real data
  useEffect(() => {
    if (!reportData || reportData.latestResults.length === 0) return;

    const inputs = reportData.latestResults.map((r: LabResult) => ({
      testName: r.testName,
      value: r.value,
    }));

    apiService
      .getPercentiles(inputs)
      .then(setPercentiles)
      .catch((err) => {
        // Percentile enrichment is non-critical — continue without it
        console.warn('Percentile fetch failed:', err);
      });
  }, [reportData]);

  return (
    <div className="min-h-screen bg-background">
      {/* Navigation */}
      <NavBar user={user} />

      {/* Demo data banner */}
      {isUsingMockData && (
        <div className="border-b bg-muted/40">
          <div className="max-w-7xl mx-auto px-4 md:px-6 py-2.5 flex items-center justify-between gap-3 text-sm text-muted-foreground">
            <span>Viewing demo data — upload your own lab report to see your results.</span>
            <Button variant="outline" size="sm" className="h-7 text-xs shrink-0" onClick={() => navigate('/upload')}>
              Upload PDF
            </Button>
          </div>
        </div>
      )}

      {/* Main content
          For mock data: MedicalDashboard manages its own padding/layout.
          For real data: we provide our own padded container. */}
      {isUsingMockData ? (
        <MedicalDashboard />
      ) : (
        <div className="p-4 md:p-6">
          <div className="max-w-7xl mx-auto">
            <RealDataDashboard reportData={reportData} percentiles={percentiles} />
          </div>
        </div>
      )}
    </div>
  );
};

export default Dashboard;
