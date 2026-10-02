import { Card, CardContent } from '@/components/ui/card';
import { Activity } from 'lucide-react';

interface HealthScoreCardProps {
  score: number | null;
  summary: string;
}

export function HealthScoreCard({ score, summary }: HealthScoreCardProps) {
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
