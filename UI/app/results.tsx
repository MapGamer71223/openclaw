import React, { useEffect, useState } from 'react';
import { ActivityIndicator, Image, Pressable, StyleSheet, Text, View } from 'react-native';
import { router, useLocalSearchParams } from 'expo-router';
import { Feather, MaterialCommunityIcons } from '@expo/vector-icons';
import { useColors } from '@/hooks/useColors';
import { useInvestigations } from '@/context/InvestigationContext';
import { ErrorState, Header, MetricCard, ScrollScreen, verdictConfig, VerdictBadge } from '@/components/ui';
import { getInvestigationDetail, originalMediaUrl } from '@/services/investigationService';
import {
  AIDetectionDetails,
  BackendInvestigationDetail,
  ForensicDetails,
  Investigation,
  MetadataDetails,
  mapAIDetection,
  mapForensics,
  mapInvestigation,
  mapMetadata,
} from '@/types/investigation';
import { ApiError } from '@/services/api';

const tabs = ['Overview', 'Forensics', 'Sources', 'Timeline'];

export default function ResultsScreen() {
  const colors = useColors();
  const params = useLocalSearchParams<{ id?: string }>();
  const { current, investigations } = useInvestigations();
  const id = params.id ?? current?.id ?? investigations[0]?.id;

  const [item, setItem] = useState<Investigation | null>(null);
  const [detection, setDetection] = useState<AIDetectionDetails | null>(null);
  const [forensics, setForensics] = useState<ForensicDetails | null>(null);
  const [metadata, setMetadata] = useState<MetadataDetails | null>(null);
  const [sourceCount, setSourceCount] = useState(0);
  const [earliestSourceDate, setEarliestSourceDate] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState('Overview');

  const load = React.useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      const detail: BackendInvestigationDetail = await getInvestigationDetail(id);
      setItem(mapInvestigation(detail, originalMediaUrl(detail.id)));
      setDetection(detail.ai_detection ? mapAIDetection(detail.ai_detection) : null);
      setForensics(detail.forensic_results ? mapForensics(detail.forensic_results) : null);
      setMetadata(detail.media_asset ? mapMetadata(detail.media_asset) : null);
      setSourceCount(detail.sources.length);
      const withDates = detail.sources.map((s) => s.publication_date).filter(Boolean) as string[];
      setEarliestSourceDate(withDates.length ? withDates.sort()[0] : null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not load investigation results.');
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  if (!id) {
    return (
      <ScrollScreen>
        <Header title="Investigation results" onBack={() => router.back()} />
        <Text style={{ color: colors.foreground }}>No result available.</Text>
      </ScrollScreen>
    );
  }

  if (loading && !item) {
    return (
      <ScrollScreen>
        <Header title="Investigation results" onBack={() => router.back()} />
        <View style={styles.loading}>
          <ActivityIndicator color={colors.primary} />
        </View>
      </ScrollScreen>
    );
  }

  if (error && !item) {
    return (
      <ScrollScreen>
        <Header title="Investigation results" onBack={() => router.back()} />
        <ErrorState title="Couldn't load results" description={error} onRetry={load} />
      </ScrollScreen>
    );
  }

  if (!item) return null;

  const openTab = (selected: string) => {
    setTab(selected);
    if (selected === 'Forensics') router.push({ pathname: '/analysis/[type]', params: { type: 'forensics', investigationId: id } });
    if (selected === 'Sources') router.push({ pathname: '/analysis/[type]', params: { type: 'sources', investigationId: id } });
    if (selected === 'Timeline') router.push({ pathname: '/analysis/[type]', params: { type: 'timeline', investigationId: id } });
  };

  const config = verdictConfig[item.verdict];
  const verdictDescriptions: Record<typeof item.verdict, string> = {
    'AI Generated': 'This media contains strong signals consistent with synthetic generation.',
    'AI Altered': 'This media shows signs of manipulation or partial synthetic alteration.',
    'Likely Authentic': 'This media shows no strong signals of AI generation or manipulation.',
    Inconclusive: 'The available signals were not strong enough to reach a confident verdict.',
    'Analysis Unavailable': 'Analysis could not be completed for this media.',
  };

  return (
    <ScrollScreen>
      <Header
        title="Investigation results"
        subtitle={item.filename}
        onBack={() => router.back()}
        right={
          <Pressable style={[styles.share, { backgroundColor: colors.surface }]}>
            <Feather name="share-2" size={17} color={colors.foreground} />
          </Pressable>
        }
      />
      <View style={[styles.verdictHero, { backgroundColor: `${config.color}12`, borderColor: `${config.color}45` }]}>
        <View style={styles.heroTitleRow}>
          <View style={[styles.verdictIcon, { backgroundColor: `${config.color}22` }]}>
            <MaterialCommunityIcons name={config.icon} size={22} color={config.color} />
          </View>
          <View>
            <Text style={[styles.verdictEyebrow, { color: config.color }]}>FINAL VERDICT</Text>
            <Text style={[styles.verdictTitle, { color: colors.foreground }]}>{item.verdict.toUpperCase()}</Text>
          </View>
        </View>
        <Text style={[styles.verdictDescription, { color: colors.mutedForeground }]}>{verdictDescriptions[item.verdict]}</Text>
        <View style={styles.verdictBottom}>
          <View>
            <Text style={[styles.confidenceBig, { color: colors.foreground }]}>{item.confidence}%</Text>
            <Text style={[styles.confidenceLabel, { color: colors.mutedForeground }]}>Confidence score</Text>
          </View>
          <VerdictBadge verdict={item.verdict} />
        </View>
      </View>
      <Image source={{ uri: item.thumbnail }} style={styles.media} />
      <View style={styles.tabs}>
        {tabs.map((tabName) => (
          <Pressable key={tabName} onPress={() => openTab(tabName)} style={[styles.tab, { borderBottomColor: tab === tabName ? colors.primary : 'transparent' }]}>
            <Text style={[styles.tabText, { color: tab === tabName ? colors.primary : colors.mutedForeground }]}>{tabName}</Text>
          </Pressable>
        ))}
      </View>
      <View style={styles.metricGrid}>
        <MetricCard
          icon="creation"
          label="AI Detection"
          value={detection ? `${detection.probability}%` : 'Pending'}
          detail={detection ? `${detection.confidence} confidence` : 'Not yet available'}
          color={colors.destructive}
        />
        <MetricCard
          icon="shield-alert-outline"
          label="Forensic score"
          value={forensics?.forensicScore != null ? `${forensics.forensicScore} / 100` : 'Pending'}
          detail={forensics ? (forensics.suspiciousIndicators.length ? `${forensics.suspiciousIndicators.length} indicator(s) found` : 'No indicators found') : 'Not yet available'}
          color={colors.orange}
        />
        <MetricCard
          icon="file-cog-outline"
          label="Metadata"
          value={metadata ? (metadata.gpsPresent || metadata.cameraInfo ? 'Available' : 'Partial') : 'Unavailable'}
          detail={metadata?.sha256 ? `SHA-256 ${metadata.sha256.slice(0, 10)}…` : 'No metadata extracted'}
          color={colors.success}
        />
        <MetricCard
          icon="source-branch"
          label="Source discovery"
          value={`${sourceCount} found`}
          detail={earliestSourceDate ? `Earliest ${earliestSourceDate}` : 'No sources found yet'}
          color={colors.primary}
        />
      </View>
      <Pressable
        onPress={() => router.push({ pathname: '/analysis/[type]', params: { type: 'ai', investigationId: id } })}
        style={[styles.detailButton, { backgroundColor: colors.surface, borderColor: colors.border }]}
      >
        <View style={[styles.detailIcon, { backgroundColor: `${colors.destructive}18` }]}>
          <MaterialCommunityIcons name="creation" size={18} color={colors.destructive} />
        </View>
        <View style={styles.detailCopy}>
          <Text style={[styles.detailTitle, { color: colors.foreground }]}>View AI detection details</Text>
          <Text style={[styles.detailText, { color: colors.mutedForeground }]}>Inspect the signals behind this verdict</Text>
        </View>
        <Feather name="arrow-up-right" size={17} color={colors.primary} />
      </Pressable>
      <Pressable
        onPress={() => router.push({ pathname: '/analysis/[type]', params: { type: 'propagation', investigationId: id } })}
        style={[styles.detailButton, { backgroundColor: colors.surface, borderColor: colors.border }]}
      >
        <View style={[styles.detailIcon, { backgroundColor: `${colors.primary}18` }]}>
          <MaterialCommunityIcons name="graph-outline" size={18} color={colors.primary} />
        </View>
        <View style={styles.detailCopy}>
          <Text style={[styles.detailTitle, { color: colors.foreground }]}>View propagation map</Text>
          <Text style={[styles.detailText, { color: colors.mutedForeground }]}>See how this media traveled online</Text>
        </View>
        <Feather name="arrow-up-right" size={17} color={colors.primary} />
      </Pressable>
    </ScrollScreen>
  );
}

const styles = StyleSheet.create({
  loading: { paddingVertical: 60, alignItems: 'center' },
  share: { width: 38, height: 38, borderRadius: 13, alignItems: 'center', justifyContent: 'center' },
  verdictHero: { borderRadius: 22, borderWidth: 1, padding: 18 },
  heroTitleRow: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  verdictIcon: { width: 45, height: 45, borderRadius: 15, alignItems: 'center', justifyContent: 'center' },
  verdictEyebrow: { fontSize: 9, fontFamily: 'Inter_700Bold', letterSpacing: 1.1 },
  verdictTitle: { fontSize: 15, fontFamily: 'Inter_700Bold', marginTop: 4 },
  verdictDescription: { fontSize: 11, lineHeight: 16, fontFamily: 'Inter_400Regular', marginTop: 17 },
  verdictBottom: { flexDirection: 'row', alignItems: 'flex-end', justifyContent: 'space-between', marginTop: 18 },
  confidenceBig: { fontSize: 30, fontFamily: 'Inter_700Bold' },
  confidenceLabel: { fontSize: 10, fontFamily: 'Inter_400Regular', marginTop: -2 },
  media: { height: 168, width: '100%', borderRadius: 20, marginTop: 12 },
  tabs: { flexDirection: 'row', marginTop: 18, borderBottomWidth: 1, borderBottomColor: '#273440' },
  tab: { flex: 1, alignItems: 'center', paddingBottom: 12, borderBottomWidth: 2 },
  tabText: { fontSize: 10, fontFamily: 'Inter_600SemiBold' },
  metricGrid: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', marginTop: 17 },
  detailButton: { borderRadius: 17, borderWidth: 1, padding: 12, flexDirection: 'row', alignItems: 'center', gap: 11, marginTop: 8 },
  detailIcon: { width: 37, height: 37, borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
  detailCopy: { flex: 1 },
  detailTitle: { fontSize: 12, fontFamily: 'Inter_700Bold' },
  detailText: { fontSize: 10, fontFamily: 'Inter_400Regular', marginTop: 4 },
});
