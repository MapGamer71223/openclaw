import React, { useEffect, useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';
import { useLocalSearchParams, router } from 'expo-router';
import { Feather, MaterialCommunityIcons } from '@expo/vector-icons';
import { useColors } from '@/hooks/useColors';
import { useInvestigations } from '@/context/InvestigationContext';
import {
  getAIDetection,
  getForensics,
  getPropagationGraph,
  getSources,
  getTimeline,
} from '@/services/investigationService';
import { ErrorState, EmptyState, Header, ProgressRing, ScrollScreen, SourceCard } from '@/components/ui';
import { ApiError } from '@/services/api';
import {
  AIDetectionDetails,
  ForensicDetails,
  PropagationGraph,
  PropagationNode,
  SourceMatch,
  TimelineEntry,
} from '@/types/investigation';

const SIGNAL_ICONS: (keyof typeof MaterialCommunityIcons.glyphMap)[] = ['blur-radial', 'vector-polyline', 'grid-off', 'waveform', 'texture-box'];

function useAsync<T>(loader: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const run = React.useCallback(() => {
    setLoading(true);
    setError(null);
    loader()
      .then((result) => setData(result))
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Something went wrong loading this data.'))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    run();
  }, [run]);

  return { data, loading, error, retry: run };
}

function Loading() {
  const colors = useColors();
  return (
    <View style={styles.loadingBox}>
      <ActivityIndicator color={colors.primary} />
    </View>
  );
}

function AIDetails({ id }: { id: string }) {
  const colors = useColors();
  const { data, loading, error, retry } = useAsync<AIDetectionDetails | null>(() => getAIDetection(id), [id]);

  if (loading) return <Loading />;
  if (error) return <ErrorState title="Couldn't load AI detection" description={error} onRetry={retry} />;
  if (!data) return <EmptyState icon="cpu" title="Detection pending" description="AI detection has not run for this investigation yet." />;

  const verdictColor = data.classification.includes('AI') ? colors.destructive : data.classification === 'Likely Authentic' ? colors.success : colors.warning;

  return (
    <>
      <View style={[styles.aiHero, { backgroundColor: colors.card, borderColor: colors.border }]}>
        <ProgressRing progress={data.probability} size={142} />
        <Text style={[styles.aiTitle, { color: colors.foreground }]}>Probability of {data.classification.toLowerCase()}</Text>
        <Text style={[styles.aiCopy, { color: colors.mutedForeground }]}>
          {data.isDemo
            ? 'This result was produced by the demo detector for illustration purposes.'
            : `Model confidence: ${data.confidence}.`}
        </Text>
      </View>
      {data.signals.length ? (
        <>
          <Text style={[styles.heading, { color: colors.foreground }]}>Detection signals</Text>
          {data.signals.map((signal, index) => (
            <View key={signal} style={[styles.signalCard, { backgroundColor: colors.card, borderColor: colors.border }]}>
              <View style={[styles.signalIcon, { backgroundColor: `${verdictColor}18` }]}>
                <MaterialCommunityIcons name={SIGNAL_ICONS[index % SIGNAL_ICONS.length]} size={18} color={verdictColor} />
              </View>
              <View style={styles.signalCopy}>
                <Text style={[styles.signalTitle, { color: colors.foreground }]}>{signal}</Text>
              </View>
            </View>
          ))}
        </>
      ) : null}
      <View style={[styles.modelCard, { backgroundColor: colors.surface }]}>
        <Text style={[styles.modelLabel, { color: colors.mutedForeground }]}>MODEL INFORMATION</Text>
        <Text style={[styles.modelName, { color: colors.foreground }]}>{data.modelName}</Text>
        <Text style={[styles.modelDetail, { color: colors.mutedForeground }]}>
          {data.signals.length ? `Analysis found ${data.signals.length} signal(s)` : 'No individual signals reported'} · detector: {data.detectorStatus}
        </Text>
      </View>
    </>
  );
}

function scoreCaption(score: number | null, colors: ReturnType<typeof useColors>) {
  if (score == null) return { text: 'Not available', color: colors.mutedForeground };
  if (score >= 60) return { text: 'Highly suspicious', color: colors.destructive };
  if (score >= 30) return { text: 'Some anomalies found', color: colors.orange };
  return { text: 'Looks clean', color: colors.success };
}

function Forensics({ id }: { id: string }) {
  const colors = useColors();
  const { data, loading, error, retry } = useAsync<ForensicDetails | null>(() => getForensics(id), [id]);

  if (loading) return <Loading />;
  if (error) return <ErrorState title="Couldn't load forensic results" description={error} onRetry={retry} />;
  if (!data) return <EmptyState icon="shield" title="Forensics pending" description="Forensic analysis has not run for this investigation yet." />;

  const caption = scoreCaption(data.forensicScore, colors);

  return (
    <>
      <View style={[styles.scoreCard, { backgroundColor: colors.card, borderColor: colors.border }]}>
        <View>
          <Text style={[styles.scoreLabel, { color: colors.mutedForeground }]}>FORENSIC INTEGRITY SCORE</Text>
          <Text style={[styles.score, { color: caption.color }]}>{data.forensicScore ?? '—'}<Text style={[styles.scoreOut, { color: colors.mutedForeground }]}> / 100</Text></Text>
          <Text style={[styles.scoreCaption, { color: caption.color }]}>{caption.text}</Text>
        </View>
        <MaterialCommunityIcons name="shield-alert-outline" size={44} color={caption.color} />
      </View>
      {data.metrics.length ? (
        data.metrics.map((metric) => (
          <View key={metric.label} style={[styles.forensic, { backgroundColor: colors.card, borderColor: colors.border }]}>
            <View style={styles.metricLine}>
              <Text style={[styles.metricLabel, { color: colors.foreground }]}>{metric.label}</Text>
              <Text style={[styles.metricValue, { color: colors.orange }]}>{metric.value}</Text>
            </View>
            <View style={[styles.forensicTrack, { backgroundColor: colors.muted }]}>
              <View style={[styles.forensicFill, { width: `${Math.min(100, metric.pct + 12)}%`, backgroundColor: colors.orange }]} />
            </View>
            <Text style={[styles.forensicStatus, { color: colors.mutedForeground }]}>{metric.status}</Text>
          </View>
        ))
      ) : (
        <Text style={[styles.forensicStatus, { color: colors.mutedForeground, marginTop: 8 }]}>No individual forensic metrics were returned for this media type.</Text>
      )}
      {data.suspiciousIndicators.length ? (
        <>
          <Text style={[styles.heading, { color: colors.foreground }]}>Suspicious indicators</Text>
          <View style={styles.chips}>
            {data.suspiciousIndicators.map((chip) => (
              <View key={chip} style={[styles.chip, { backgroundColor: `${colors.orange}15` }]}>
                <View style={[styles.chipDot, { backgroundColor: colors.orange }]} />
                <Text style={[styles.chipText, { color: colors.orange }]}>{chip}</Text>
              </View>
            ))}
          </View>
        </>
      ) : null}
    </>
  );
}

function Sources({ id }: { id: string }) {
  const colors = useColors();
  const { data, loading, error, retry } = useAsync<SourceMatch[]>(() => getSources(id), [id]);

  if (loading) return <Loading />;
  if (error) return <ErrorState title="Couldn't load sources" description={error} onRetry={retry} />;
  const sources = data ?? [];
  const earliest = sources
    .map((s) => s.date)
    .filter((d) => d && d !== 'Unknown date')
    .sort()[0];

  return (
    <>
      <View style={[styles.sourcesSummary, { backgroundColor: colors.card, borderColor: colors.border }]}>
        <View>
          <Text style={[styles.sourcesCount, { color: colors.foreground }]}>{sources.length}</Text>
          <Text style={[styles.sourcesLabel, { color: colors.mutedForeground }]}>sources found</Text>
        </View>
        <View style={styles.summaryDivider} />
        <View>
          <Text style={[styles.earliest, { color: colors.foreground }]}>{earliest ?? 'Unknown'}</Text>
          <Text style={[styles.sourcesLabel, { color: colors.mutedForeground }]}>earliest source</Text>
        </View>
      </View>
      <Text style={[styles.heading, { color: colors.foreground }]}>Closest matches</Text>
      {sources.length ? (
        sources.map((source) => <SourceCard key={source.id} source={source} />)
      ) : (
        <EmptyState icon="search" title="No sources found" description="No matching sources have been discovered for this media yet." />
      )}
    </>
  );
}

function Timeline({ id }: { id: string }) {
  const colors = useColors();
  const { data, loading, error, retry } = useAsync<TimelineEntry[]>(() => getTimeline(id), [id]);

  if (loading) return <Loading />;
  if (error) return <ErrorState title="Couldn't load the timeline" description={error} onRetry={retry} />;
  const timeline = data ?? [];
  if (!timeline.length) return <EmptyState icon="clock" title="No events yet" description="This investigation hasn't logged any events yet." />;

  return (
    <View style={styles.timeline}>
      {timeline.map((entry, index) => (
        <View key={`${entry.title}-${index}`} style={styles.timelineRow}>
          <View style={styles.timelineRail}>
            <View style={[styles.timelineDot, { backgroundColor: colors.primary }]}>
              <MaterialCommunityIcons name={entry.icon as keyof typeof MaterialCommunityIcons.glyphMap} size={13} color={colors.black} />
            </View>
            {index < timeline.length - 1 ? <View style={[styles.timelineLine, { backgroundColor: colors.border }]} /> : null}
          </View>
          <View style={styles.timelineBody}>
            <View style={styles.timelineTop}>
              <Text style={[styles.timelineTitle, { color: colors.foreground }]}>{entry.title}</Text>
              <Text style={[styles.timelineTime, { color: colors.mutedForeground }]}>{entry.time}</Text>
            </View>
            <Text style={[styles.timelineAgent, { color: colors.primary }]}>{entry.agent}</Text>
            {entry.description ? <Text style={[styles.timelineDescription, { color: colors.mutedForeground }]}>{entry.description}</Text> : null}
          </View>
        </View>
      ))}
    </View>
  );
}

function nodeIcon(node: PropagationNode): keyof typeof MaterialCommunityIcons.glyphMap {
  const platform = (node.platform ?? '').toLowerCase();
  if (platform.includes('x') || platform.includes('twitter')) return 'twitter';
  if (platform.includes('facebook')) return 'facebook';
  if (platform.includes('instagram')) return 'instagram';
  if (platform.includes('reddit')) return 'reddit';
  if (node.type === 'source') return 'shield-check-outline';
  return 'newspaper-variant-outline';
}

function nodeLabel(node: PropagationNode): string {
  if (node.platform) return node.platform;
  return node.type === 'source' ? 'Original source' : 'Article';
}

function Propagation({ id }: { id: string }) {
  const colors = useColors();
  const { data, loading, error, retry } = useAsync<PropagationGraph>(() => getPropagationGraph(id), [id]);

  if (loading) return <Loading />;
  if (error) return <ErrorState title="Couldn't load propagation data" description={error} onRetry={retry} />;

  const nodes = data?.nodes ?? [];
  const edges = data?.edges ?? [];

  if (!nodes.length) {
    return <EmptyState icon="share-2" title="No propagation data" description="No propagation data was discovered for this investigation." />;
  }

  const timestamps = nodes.map((n) => n.timestamp).filter(Boolean) as string[];
  const firstDetected = timestamps.length ? timestamps.sort()[0] : 'Unknown';
  const platformCount = new Set(nodes.map((n) => n.platform).filter(Boolean)).size;

  // Simple, mobile-friendly layout for a small graph. Beyond a handful of
  // nodes a positioned diagram stops being legible on a phone, so we fall
  // back to a scannable list instead of pulling in a heavy graph library.
  const useDiagram = nodes.length <= 5;
  const positions = [
    { x: 0, y: 65 },
    { x: 126, y: 10 },
    { x: 126, y: 119 },
    { x: 248, y: 10 },
    { x: 248, y: 119 },
  ];

  return (
    <>
      {useDiagram ? (
        <View style={[styles.mapCard, { backgroundColor: colors.card, borderColor: colors.border }]}>
          {nodes.length > 1 ? (
            <>
              <View style={[styles.mapLine, { backgroundColor: colors.border, transform: [{ rotate: '-24deg' }] }]} />
              {nodes.length > 2 ? <View style={[styles.mapLine, { backgroundColor: colors.border, transform: [{ rotate: '24deg' }] }]} /> : null}
              {nodes.length > 3 ? <View style={[styles.mapLine, { backgroundColor: colors.border, left: 164, width: 92, transform: [{ rotate: '-24deg' }] }]} /> : null}
              {nodes.length > 4 ? <View style={[styles.mapLine, { backgroundColor: colors.border, left: 164, width: 92, transform: [{ rotate: '24deg' }] }]} /> : null}
            </>
          ) : null}
          {nodes.map((node, index) => {
            const color = index === 0 ? colors.primary : colors.warning;
            const pos = positions[index] ?? positions[positions.length - 1];
            return (
              <View key={node.id} style={[styles.mapNode, { left: pos.x, top: pos.y }]}>
                <View style={[styles.nodeIcon, { backgroundColor: `${color}1D`, borderColor: `${color}70` }]}>
                  <MaterialCommunityIcons name={nodeIcon(node)} size={16} color={color} />
                </View>
                <Text style={[styles.nodeLabel, { color: colors.foreground }]} numberOfLines={2}>{nodeLabel(node)}</Text>
              </View>
            );
          })}
        </View>
      ) : (
        <View style={styles.nodeList}>
          {nodes.map((node, index) => (
            <View key={node.id} style={[styles.nodeListRow, { backgroundColor: colors.card, borderColor: colors.border }]}>
              <View style={[styles.nodeIcon, { backgroundColor: `${colors.primary}1D`, borderColor: `${colors.primary}70` }]}>
                <MaterialCommunityIcons name={nodeIcon(node)} size={16} color={index === 0 ? colors.primary : colors.mutedForeground} />
              </View>
              <View style={styles.nodeListBody}>
                <Text style={[styles.nodeListTitle, { color: colors.foreground }]}>{nodeLabel(node)}</Text>
                <Text style={[styles.nodeListMeta, { color: colors.mutedForeground }]} numberOfLines={1}>
                  {node.timestamp ?? 'Unknown date'}{node.similarityScore != null ? ` · ${Math.round(node.similarityScore * 100)}% similar` : ''}
                </Text>
              </View>
            </View>
          ))}
        </View>
      )}
      <View style={styles.mapStats}>
        <View style={[styles.mapStat, { backgroundColor: colors.card, borderColor: colors.border }]}>
          <Text style={[styles.mapStatValue, { color: colors.foreground }]}>{firstDetected}</Text>
          <Text style={[styles.mapStatLabel, { color: colors.mutedForeground }]}>First detected</Text>
        </View>
        <View style={[styles.mapStat, { backgroundColor: colors.card, borderColor: colors.border }]}>
          <Text style={[styles.mapStatValue, { color: colors.foreground }]}>{platformCount}</Text>
          <Text style={[styles.mapStatLabel, { color: colors.mutedForeground }]}>Platforms</Text>
        </View>
        <View style={[styles.mapStat, { backgroundColor: colors.card, borderColor: colors.border }]}>
          <Text style={[styles.mapStatValue, { color: colors.foreground }]}>{edges.length}</Text>
          <Text style={[styles.mapStatLabel, { color: colors.mutedForeground }]}>Connections</Text>
        </View>
      </View>
      <View style={[styles.mapNote, { backgroundColor: `${colors.primary}12` }]}>
        <MaterialCommunityIcons name="information-outline" size={17} color={colors.primary} />
        <Text style={[styles.mapNoteText, { color: colors.mutedForeground }]}>
          The highlighted node is the source with the highest confidence. Connections reflect discovered propagation relationships between matches.
        </Text>
      </View>
    </>
  );
}

export default function AnalysisScreen() {
  const params = useLocalSearchParams<{ type: string; investigationId?: string }>();
  const { current } = useInvestigations();
  const id = params.investigationId ?? current?.id;
  const type = params.type;

  const titles: Record<string, [string, string]> = {
    ai: ['AI detection', 'Signal intelligence'],
    forensics: ['Forensic analysis', 'Integrity and manipulation signals'],
    sources: ['Source discovery', 'Trace media across the open web'],
    timeline: ['Investigation timeline', 'A complete chain of evidence'],
    propagation: ['Propagation map', 'How this media spread online'],
  };
  const [title, subtitle] = titles[type ?? 'ai'] ?? titles.ai;

  if (!id) {
    return (
      <ScrollScreen>
        <Header title={title} subtitle={subtitle} onBack={() => router.back()} />
        <EmptyState icon="alert-triangle" title="No investigation selected" description="Open this screen from an investigation's results to see its details." />
      </ScrollScreen>
    );
  }

  return (
    <ScrollScreen>
      <Header title={title} subtitle={subtitle} onBack={() => router.back()} />
      {type === 'forensics' ? <Forensics id={id} /> : type === 'sources' ? <Sources id={id} /> : type === 'timeline' ? <Timeline id={id} /> : type === 'propagation' ? <Propagation id={id} /> : <AIDetails id={id} />}
    </ScrollScreen>
  );
}

const styles = StyleSheet.create({
  loadingBox: { paddingVertical: 60, alignItems: 'center' },
  aiHero: { borderRadius: 21, borderWidth: 1, padding: 22, alignItems: 'center' },
  aiTitle: { fontSize: 15, fontFamily: 'Inter_700Bold', marginTop: 20, textAlign: 'center' },
  aiCopy: { fontSize: 11, lineHeight: 17, fontFamily: 'Inter_400Regular', textAlign: 'center', marginTop: 8 },
  heading: { fontSize: 15, fontFamily: 'Inter_700Bold', marginTop: 26, marginBottom: 12 },
  signalCard: { borderRadius: 17, borderWidth: 1, padding: 12, flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 9 },
  signalIcon: { width: 38, height: 38, borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
  signalCopy: { flex: 1 },
  signalTitle: { fontSize: 11, fontFamily: 'Inter_700Bold' },
  signalDetail: { fontSize: 9, lineHeight: 13, fontFamily: 'Inter_400Regular', marginTop: 4 },
  modelCard: { padding: 15, borderRadius: 16, marginTop: 7 },
  modelLabel: { fontSize: 8, fontFamily: 'Inter_700Bold', letterSpacing: 1.2 },
  modelName: { fontSize: 11, fontFamily: 'Inter_700Bold', marginTop: 8 },
  modelDetail: { fontSize: 10, fontFamily: 'Inter_400Regular', marginTop: 4 },
  scoreCard: { borderWidth: 1, borderRadius: 20, padding: 19, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  scoreLabel: { fontSize: 9, fontFamily: 'Inter_700Bold', letterSpacing: 1 },
  score: { fontSize: 36, fontFamily: 'Inter_700Bold', marginTop: 7 },
  scoreOut: { fontSize: 14, fontFamily: 'Inter_500Medium' },
  scoreCaption: { fontSize: 10, fontFamily: 'Inter_600SemiBold' },
  forensic: { borderWidth: 1, borderRadius: 17, padding: 15, marginTop: 10 },
  metricLine: { flexDirection: 'row', justifyContent: 'space-between' },
  metricLabel: { fontSize: 11, fontFamily: 'Inter_600SemiBold' },
  metricValue: { fontSize: 11, fontFamily: 'Inter_700Bold' },
  forensicTrack: { height: 6, borderRadius: 5, overflow: 'hidden', marginTop: 12 },
  forensicFill: { height: '100%', borderRadius: 5 },
  forensicStatus: { fontSize: 9, fontFamily: 'Inter_400Regular', marginTop: 8 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 10, paddingVertical: 8, borderRadius: 9 },
  chipDot: { width: 5, height: 5, borderRadius: 3 },
  chipText: { fontSize: 9, fontFamily: 'Inter_600SemiBold' },
  sourcesSummary: { borderRadius: 19, borderWidth: 1, padding: 18, flexDirection: 'row', alignItems: 'center' },
  sourcesCount: { fontSize: 28, fontFamily: 'Inter_700Bold' },
  sourcesLabel: { fontSize: 10, fontFamily: 'Inter_400Regular', marginTop: 2 },
  summaryDivider: { height: 40, width: 1, backgroundColor: '#273440', marginHorizontal: 22 },
  earliest: { fontSize: 13, fontFamily: 'Inter_700Bold' },
  timeline: { paddingTop: 7 },
  timelineRow: { flexDirection: 'row', minHeight: 94 },
  timelineRail: { width: 36, alignItems: 'center', position: 'relative' },
  timelineDot: { width: 27, height: 27, borderRadius: 14, alignItems: 'center', justifyContent: 'center', zIndex: 1 },
  timelineLine: { position: 'absolute', top: 27, bottom: -2, width: 1 },
  timelineBody: { flex: 1, paddingLeft: 10, paddingBottom: 22 },
  timelineTop: { flexDirection: 'row', justifyContent: 'space-between', gap: 8 },
  timelineTitle: { fontSize: 12, fontFamily: 'Inter_700Bold', flex: 1 },
  timelineTime: { fontSize: 9, fontFamily: 'Inter_400Regular' },
  timelineAgent: { fontSize: 9, fontFamily: 'Inter_600SemiBold', marginTop: 6 },
  timelineDescription: { fontSize: 10, fontFamily: 'Inter_400Regular', marginTop: 5 },
  mapCard: { height: 240, borderRadius: 20, borderWidth: 1, position: 'relative', overflow: 'hidden' },
  mapLine: { position: 'absolute', left: 58, top: 119, width: 88, height: 1 },
  mapNode: { position: 'absolute', width: 82, alignItems: 'center' },
  nodeIcon: { width: 37, height: 37, borderRadius: 13, borderWidth: 1, alignItems: 'center', justifyContent: 'center' },
  nodeLabel: { fontSize: 9, lineHeight: 12, fontFamily: 'Inter_600SemiBold', textAlign: 'center', marginTop: 6 },
  nodeList: { gap: 9 },
  nodeListRow: { flexDirection: 'row', alignItems: 'center', gap: 11, borderRadius: 16, borderWidth: 1, padding: 12 },
  nodeListBody: { flex: 1 },
  nodeListTitle: { fontSize: 12, fontFamily: 'Inter_700Bold' },
  nodeListMeta: { fontSize: 10, fontFamily: 'Inter_400Regular', marginTop: 3 },
  mapStats: { flexDirection: 'row', gap: 8, marginTop: 11 },
  mapStat: { flex: 1, borderRadius: 14, borderWidth: 1, padding: 11 },
  mapStatValue: { fontSize: 16, fontFamily: 'Inter_700Bold' },
  mapStatLabel: { fontSize: 8, fontFamily: 'Inter_400Regular', marginTop: 5 },
  mapNote: { marginTop: 13, borderRadius: 14, padding: 13, flexDirection: 'row', gap: 8 },
  mapNoteText: { flex: 1, fontSize: 10, lineHeight: 15, fontFamily: 'Inter_400Regular' },
});
