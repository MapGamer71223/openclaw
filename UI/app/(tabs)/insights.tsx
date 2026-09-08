import React, { useEffect, useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';
import { MaterialCommunityIcons } from '@expo/vector-icons';
import { useColors } from '@/hooks/useColors';
import { useInvestigations } from '@/context/InvestigationContext';
import { ErrorState, MiniBarChart, ScrollScreen, SectionHeader, StatCard } from '@/components/ui';
import { getInsights } from '@/services/investigationService';
import { InsightsSummary } from '@/types/investigation';
import { ApiError } from '@/services/api';

const DAY_LABELS = ['S', 'M', 'T', 'W', 'T', 'F', 'S'];

function last7DayCounts(createdAtDates: string[]): { counts: number[]; labels: string[]; total: number; previousTotal: number } {
  const now = new Date();
  const counts: number[] = [];
  const labels: string[] = [];
  for (let i = 6; i >= 0; i -= 1) {
    const day = new Date(now);
    day.setDate(now.getDate() - i);
    labels.push(DAY_LABELS[day.getDay()]);
    const count = createdAtDates.filter((iso) => new Date(iso).toDateString() === day.toDateString()).length;
    counts.push(count);
  }
  const total = counts.reduce((sum, n) => sum + n, 0);

  const previousCounts: number[] = [];
  for (let i = 13; i >= 7; i -= 1) {
    const day = new Date(now);
    day.setDate(now.getDate() - i);
    const count = createdAtDates.filter((iso) => new Date(iso).toDateString() === day.toDateString()).length;
    previousCounts.push(count);
  }
  const previousTotal = previousCounts.reduce((sum, n) => sum + n, 0);

  return { counts, labels, total, previousTotal };
}

export default function InsightsScreen() {
  const colors = useColors();
  const { investigations, loading: historyLoading } = useInvestigations();
  const [summary, setSummary] = useState<InsightsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = React.useCallback(() => {
    setLoading(true);
    setError(null);
    getInsights(investigations)
      .then(setSummary)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Could not load insights from the backend.'))
      .finally(() => setLoading(false));
  }, [investigations]);

  useEffect(() => {
    if (!historyLoading) load();
  }, [historyLoading, load]);

  if (loading && !summary) {
    return (
      <ScrollScreen>
        <Text style={[styles.title, { color: colors.foreground }]}>Insights</Text>
        <View style={styles.loadingBox}><ActivityIndicator color={colors.primary} /></View>
      </ScrollScreen>
    );
  }

  if (error && !summary) {
    return (
      <ScrollScreen>
        <Text style={[styles.title, { color: colors.foreground }]}>Insights</Text>
        <ErrorState title="Couldn't load insights" description={error} onRetry={load} />
      </ScrollScreen>
    );
  }

  if (!summary) return null;

  const total = summary.totalInvestigations;
  const pct = (n: number) => (total > 0 ? Math.round((n / total) * 100) : 0);
  const legend: [string, string, number][] = [
    ['AI Generated', colors.destructive, summary.aiGenerated],
    ['AI Altered', colors.orange, summary.aiAltered],
    ['Authentic', colors.success, summary.authentic],
    ['Inconclusive', colors.warning, summary.inconclusive],
  ];
  const dominant = legend.reduce((best, entry) => (entry[2] > best[2] ? entry : best), legend[0]);

  const activity = last7DayCounts(investigations.map((i) => i.createdAt));
  const trend =
    activity.previousTotal > 0
      ? `${activity.total >= activity.previousTotal ? '↑' : '↓'} ${Math.abs(Math.round(((activity.total - activity.previousTotal) / activity.previousTotal) * 100))}% vs last week`
      : activity.total > 0
        ? 'No data for last week yet'
        : null;

  return (
    <ScrollScreen>
      <Text style={[styles.title, { color: colors.foreground }]}>Insights</Text>
      <Text style={[styles.subtitle, { color: colors.mutedForeground }]}>Your media intelligence at a glance</Text>
      <View style={styles.stats}>
        <StatCard label="Total investigations" value={`${total}`} />
        <StatCard label="AI generated" value={`${summary.aiGenerated}`} trend={total ? `${pct(summary.aiGenerated)}% of total` : undefined} color={colors.destructive} />
        <StatCard label="AI altered" value={`${summary.aiAltered}`} trend={total ? `${pct(summary.aiAltered)}% of total` : undefined} color={colors.orange} />
        <StatCard label="Likely authentic" value={`${summary.authentic}`} trend={total ? `${pct(summary.authentic)}% of total` : undefined} color={colors.success} />
      </View>
      <SectionHeader title="Verdict distribution" />
      <View style={[styles.distribution, { backgroundColor: colors.card, borderColor: colors.border }]}>
        <View style={styles.donutWrap}>
          <View style={[styles.donut, { borderColor: dominant[1] }]}>
            <View style={[styles.donutInner, { backgroundColor: colors.card }]}>
              <Text style={[styles.donutValue, { color: colors.foreground }]}>{total ? `${pct(dominant[2])}%` : '—'}</Text>
              <Text style={[styles.donutLabel, { color: colors.mutedForeground }]}>{dominant[0]}</Text>
            </View>
          </View>
        </View>
        <View style={styles.legend}>
          {legend.map(([label, color, value]) => (
            <View key={label} style={styles.legendRow}>
              <View style={[styles.legendDot, { backgroundColor: color }]} />
              <Text style={[styles.legendLabel, { color: colors.mutedForeground }]}>{label}</Text>
              <Text style={[styles.legendValue, { color: colors.foreground }]}>{value}</Text>
            </View>
          ))}
        </View>
      </View>
      <SectionHeader title="7-day activity" />
      <View style={[styles.activity, { backgroundColor: colors.card, borderColor: colors.border }]}>
        <View style={styles.activityTop}>
          <View>
            <Text style={[styles.activityValue, { color: colors.foreground }]}>{activity.total} <Text style={[styles.activityUnit, { color: colors.mutedForeground }]}>scans</Text></Text>
            {trend ? <Text style={[styles.activityDetail, { color: activity.total >= activity.previousTotal ? colors.success : colors.destructive }]}>{trend}</Text> : null}
          </View>
          <MaterialCommunityIcons name="chart-line" size={24} color={colors.primary} />
        </View>
        <MiniBarChart values={activity.counts} labels={activity.labels} />
      </View>
      <SectionHeader title="Detection summary" />
      <View style={styles.signalRow}>
        <View style={[styles.signal, { backgroundColor: colors.card, borderColor: colors.border }]}>
          <MaterialCommunityIcons name="gauge" size={20} color={colors.accent} />
          <Text style={[styles.signalLabel, { color: colors.mutedForeground }]}>Avg. confidence</Text>
          <Text style={[styles.signalValue, { color: colors.foreground }]}>{summary.averageConfidence != null ? `${summary.averageConfidence}%` : '—'}</Text>
          <Text style={[styles.signalMeta, { color: colors.mutedForeground }]}>across completed investigations</Text>
        </View>
        <View style={[styles.signal, { backgroundColor: colors.card, borderColor: colors.border }]}>
          <MaterialCommunityIcons name="source-branch" size={20} color={colors.primary} />
          <Text style={[styles.signalLabel, { color: colors.mutedForeground }]}>Sources traced</Text>
          <Text style={[styles.signalValue, { color: colors.foreground }]}>{summary.sourcesTraced}</Text>
          <Text style={[styles.signalMeta, { color: colors.mutedForeground }]}>total, across all investigations</Text>
        </View>
      </View>
    </ScrollScreen>
  );
}

const styles = StyleSheet.create({
  title: { fontSize: 27, fontFamily: 'Inter_700Bold', letterSpacing: -0.8 },
  subtitle: { fontSize: 12, fontFamily: 'Inter_400Regular', marginTop: 5 },
  loadingBox: { paddingVertical: 60, alignItems: 'center' },
  stats: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', marginTop: 21 },
  distribution: { borderRadius: 19, borderWidth: 1, padding: 17, flexDirection: 'row', alignItems: 'center' },
  donutWrap: { width: 144, alignItems: 'center' },
  donut: { width: 116, height: 116, borderRadius: 60, borderWidth: 15, alignItems: 'center', justifyContent: 'center', transform: [{ rotate: '-35deg' }] },
  donutInner: { width: 76, height: 76, borderRadius: 40, alignItems: 'center', justifyContent: 'center', transform: [{ rotate: '35deg' }] },
  donutValue: { fontSize: 19, fontFamily: 'Inter_700Bold' },
  donutLabel: { fontSize: 8, fontFamily: 'Inter_500Medium', marginTop: 2 },
  legend: { flex: 1, gap: 11 },
  legendRow: { flexDirection: 'row', alignItems: 'center', gap: 7 },
  legendDot: { width: 7, height: 7, borderRadius: 4 },
  legendLabel: { flex: 1, fontSize: 10, fontFamily: 'Inter_400Regular' },
  legendValue: { fontSize: 11, fontFamily: 'Inter_700Bold' },
  activity: { borderRadius: 19, borderWidth: 1, padding: 17 },
  activityTop: { flexDirection: 'row', justifyContent: 'space-between' },
  activityValue: { fontSize: 25, fontFamily: 'Inter_700Bold' },
  activityUnit: { fontSize: 12, fontFamily: 'Inter_500Medium' },
  activityDetail: { fontSize: 10, fontFamily: 'Inter_600SemiBold', marginTop: 4 },
  signalRow: { flexDirection: 'row', justifyContent: 'space-between' },
  signal: { width: '48.5%', padding: 14, borderRadius: 17, borderWidth: 1, gap: 6 },
  signalLabel: { fontSize: 9, fontFamily: 'Inter_500Medium', marginTop: 5 },
  signalValue: { fontSize: 12, fontFamily: 'Inter_700Bold' },
  signalMeta: { fontSize: 9, fontFamily: 'Inter_600SemiBold' },
});
