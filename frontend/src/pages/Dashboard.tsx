import { useEffect, useState } from 'react';
import { useLocation, useNavigate, Link } from 'react-router-dom';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { MedicalDashboard } from '@/components/medical/MedicalDashboard';
import { PatientCard } from '@/components/medical/PatientCard';
import { ChatWidget } from '@/components/medical/ChatWidget';
import { useAuth } from '@/contexts/AuthContext';
import { apiService, PercentileResponse } from '@/services/api';
import { MedicalData } from '@/types/medical';
import { Upload, FileText, Stethoscope, LogOut } from 'lucide-react';

// ── Navigation bar ────────────────────────────────────────────────────────────

interface NavBarProps {
  user: { full_name: string | null; email: string } | null;
}

function NavBar({ user }: NavBarProps) {
  const navigate = useNavigate();
  const { logout } = useAuth();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

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
          {user && (
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5 h-8 text-xs"
              onClick={handleLogout}
            >
              <LogOut className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Logout</span>
            </Button>
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
  const justUploaded = locationState?.reportData ?? null;

  const [fetchedReport, setFetchedReport] = useState<MedicalData | null>(null);
  const [fetchedReportId, setFetchedReportId] = useState<string | null>(null);
  const [isLoadingLatest, setIsLoadingLatest] = useState(false);
  const [percentiles, setPercentiles] = useState<PercentileResponse | null>(null);

  // Logged-in users always see their own latest report, never the bundled
  // demo data — fetch it whenever we land here without having just
  // uploaded something (e.g. after a fresh login, or navigating here
  // directly). Anonymous visitors still see the demo for a quick look.
  useEffect(() => {
    if (!user || justUploaded) return;
    setIsLoadingLatest(true);
    apiService
      .getReports()
      .then((reports) => {
        if (reports.length === 0) return undefined;
        setFetchedReportId(reports[0].id);
        return apiService.getReport(reports[0].id);
      })
      .then((report) => setFetchedReport(report ?? null))
      .catch((err) => console.warn('Failed to fetch latest report:', err))
      .finally(() => setIsLoadingLatest(false));
  }, [user, justUploaded]);

  const activeData = justUploaded ?? fetchedReport;
  const showIntro = !user && activeData === null;

  // Fetch percentile enrichment for real data
  useEffect(() => {
    if (!activeData || activeData.latestResults.length === 0) return;

    const inputs = activeData.latestResults.map((r) => ({
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
  }, [activeData]);

  return (
    <div className="min-h-screen bg-background">
      {/* Navigation */}
      <NavBar user={user} />

      {/* Main content */}
      {showIntro ? (
        <div className="p-4 md:p-6">
          <div className="max-w-xl mx-auto pt-20 text-center space-y-5">
            <div className="inline-flex items-center justify-center w-14 h-14 bg-foreground rounded-full">
              <Stethoscope className="w-7 h-7 text-background" />
            </div>
            <h1 className="text-3xl font-semibold text-foreground">MedLab</h1>
            <p className="text-muted-foreground">
              Upload a lab report PDF and get an instant, plain-language breakdown of your
              results — with population percentile context and an AI you can ask follow-up
              questions.
            </p>
            <div className="flex items-center justify-center gap-3 pt-2">
              <Button
                size="lg"
                className="bg-foreground text-background hover:bg-foreground/90 px-6"
                onClick={() => navigate('/upload')}
              >
                Upload a Report
              </Button>
              <Link to="/login">
                <Button size="lg" variant="outline" className="px-6">
                  Sign In
                </Button>
              </Link>
            </div>
          </div>
        </div>
      ) : isLoadingLatest ? (
        <div className="p-12 text-center text-muted-foreground text-sm">Loading your reports…</div>
      ) : !activeData ? (
        <div className="p-4 md:p-6">
          <div className="max-w-2xl mx-auto pt-8 space-y-8">
            {/* Welcome header */}
            <div className="text-center space-y-2">
              <h1 className="text-2xl font-light text-foreground">
                Welcome{user?.full_name ? `, ${user.full_name.split(' ')[0]}` : ''}
              </h1>
              <p className="text-muted-foreground text-sm">
                Upload your first lab report to get started.
              </p>
            </div>

            {/* Feature highlights */}
            <div className="grid sm:grid-cols-3 gap-4">
              {[
                {
                  icon: '📊',
                  title: 'Instant Analysis',
                  desc: 'Every test value explained in plain language with normal range context.',
                },
                {
                  icon: '📈',
                  title: 'Percentile Scores',
                  desc: 'See how your results compare to the general population.',
                },
                {
                  icon: '💬',
                  title: 'Ask Questions',
                  desc: 'Chat with an AI that answers questions about your specific report.',
                },
              ].map((f) => (
                <Card key={f.title} className="border bg-card">
                  <CardContent className="pt-6 pb-5 text-center space-y-2">
                    <div className="text-3xl">{f.icon}</div>
                    <p className="text-sm font-medium text-foreground">{f.title}</p>
                    <p className="text-xs text-muted-foreground leading-relaxed">{f.desc}</p>
                  </CardContent>
                </Card>
              ))}
            </div>

            {/* CTA */}
            <div className="text-center">
              <Button
                size="lg"
                className="bg-foreground text-background hover:bg-foreground/90 px-8"
                onClick={() => navigate('/upload')}
              >
                Upload Your First Report
              </Button>
              <p className="text-xs text-muted-foreground mt-3">PDF up to 16 MB · results in under a minute</p>
            </div>
          </div>
        </div>
      ) : activeData.latestResults.length === 0 ? (
        <div className="p-4 md:p-6">
          <div className="max-w-7xl mx-auto space-y-6">
            <PatientCard patient={activeData.patientInfo} />
            <Card>
              <CardContent className="py-12 text-center text-muted-foreground text-sm">
                No lab results were extracted from this report.
              </CardContent>
            </Card>
          </div>
        </div>
      ) : (
        <MedicalDashboard
          patientInfo={activeData.patientInfo}
          latestResults={activeData.latestResults}
          testCategories={activeData.testCategories}
          healthScore={percentiles?.overall_health_score}
          healthSummary={percentiles?.summary}
        />
      )}

      <ChatWidget reportId={fetchedReportId ?? undefined} />
    </div>
  );
};

export default Dashboard;
