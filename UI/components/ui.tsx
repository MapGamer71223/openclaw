import React, { PropsWithChildren, useEffect, useRef } from 'react';
import {
  ActivityIndicator,
  Animated,
  Image,
  Linking,
  Platform,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
  ViewStyle,
} from 'react-native';
import { Feather, MaterialCommunityIcons } from '@expo/vector-icons';
import { useColors } from '@/hooks/useColors';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Investigation, SourceMatch, Verdict } from '@/types/investigation';

export function Screen({ children, style }: PropsWithChildren<{ style?: ViewStyle }>) {
  const colors = useColors();
  return <View style={[styles.screen, { backgroundColor: colors.background }, style]}>{children}</View>;
}

export function ScrollScreen({ children, style, refreshing, onRefresh }: PropsWithChildren<{ style?: ViewStyle; refreshing?: boolean; onRefresh?: () => void }>) {
  const colors = useColors();
  const insets = useSafeAreaInsets();
  const topInset = Platform.OS === 'web' ? 67 : insets.top;
  const bottomInset = Platform.OS === 'web' ? 34 : insets.bottom;
  return (
    <ScrollView
      style={[styles.screen, { backgroundColor: colors.background }]}
      contentContainerStyle={[styles.scrollContent, { paddingTop: topInset + 8, paddingBottom: bottomInset + 92 }, style]}
      showsVerticalScrollIndicator={false}
      refreshControl={onRefresh ? <RefreshControl refreshing={!!refreshing} onRefresh={onRefresh} tintColor={colors.primary} /> : undefined}
    >
      {children}
    </ScrollView>
  );
}

export function LogoMark({ small = false }: { small?: boolean }) {
  const colors = useColors();
  const size = small ? 34 : 54;
  return (
    <View style={[styles.logo, { width: size, height: size, borderRadius: size / 3, backgroundColor: colors.primary }]}>
      <MaterialCommunityIcons name="shield-check-outline" size={small ? 20 : 32} color={colors.black} />
    </View>
  );
}

export function Header({ title, subtitle, onBack, right }: { title: string; subtitle?: string; onBack?: () => void; right?: React.ReactNode }) {
  const colors = useColors();
  return (
    <View style={styles.header}>
      {onBack ? (
        <Pressable onPress={onBack} hitSlop={12} style={[styles.iconButton, { backgroundColor: colors.surface }]}><Feather name="arrow-left" size={20} color={colors.foreground} /></Pressable>
      ) : <LogoMark small />}
      <View style={styles.headerCopy}>
        <Text style={[styles.headerTitle, { color: colors.foreground }]}>{title}</Text>
        {subtitle ? <Text style={[styles.headerSubtitle, { color: colors.mutedForeground }]}>{subtitle}</Text> : null}
      </View>
      {right ?? <View style={styles.headerSpacer} />}
    </View>
  );
}

export function SectionHeader({ title, action, onAction }: { title: string; action?: string; onAction?: () => void }) {
  const colors = useColors();
  return <View style={styles.sectionHeader}><Text style={[styles.sectionTitle, { color: colors.foreground }]}>{title}</Text>{action ? <Pressable onPress={onAction}><Text style={[styles.sectionAction, { color: colors.primary }]}>{action}</Text></Pressable> : null}</View>;
}

export const verdictConfig: Record<Verdict, { color: string; icon: keyof typeof MaterialCommunityIcons.glyphMap }> = {
  'AI Generated': { color: '#EF4444', icon: 'creation' },
  'AI Altered': { color: '#F97316', icon: 'image-edit-outline' },
  'Likely Authentic': { color: '#22C55E', icon: 'check-decagram-outline' },
  'Inconclusive': { color: '#F59E0B', icon: 'help-circle-outline' },
  'Analysis Unavailable': { color: '#8C9AA8', icon: 'alert-circle-outline' },
};

export function VerdictBadge({ verdict }: { verdict: Verdict }) {
  const colors = useColors();
  const config = verdictConfig[verdict];
  return <View style={[styles.verdictBadge, { backgroundColor: `${config.color}1A` }]}><MaterialCommunityIcons name={config.icon} size={13} color={config.color} /><Text style={[styles.verdictText, { color: config.color }]}>{verdict}</Text></View>;
}

export function ConfidenceIndicator({ value, compact = false }: { value: number; compact?: boolean }) {
  const colors = useColors();
  return <View style={compact ? styles.confidenceCompact : styles.confidence}><View style={styles.confidenceRow}><Text style={[styles.caption, { color: colors.mutedForeground }]}>Confidence</Text><Text style={[styles.confidenceValue, { color: colors.foreground }]}>{value}%</Text></View><View style={[styles.progressTrack, { backgroundColor: colors.muted }]}><View style={[styles.progressFill, { width: `${value}%`, backgroundColor: value > 85 ? colors.success : value > 70 ? colors.warning : colors.orange }]} /></View></View>;
}

export function InvestigationCard({ investigation, onPress }: { investigation: Investigation; onPress?: () => void }) {
  const colors = useColors();
  return <Pressable onPress={onPress} style={({ pressed }) => [styles.investigationCard, { backgroundColor: colors.card, borderColor: colors.border, opacity: pressed ? 0.86 : 1 }]}>
    <Image source={{ uri: investigation.thumbnail }} style={styles.thumb} />
    <View style={styles.cardMain}><View style={styles.fileRow}><Text style={[styles.cardTitle, { color: colors.foreground }]} numberOfLines={1}>{investigation.filename}</Text><Feather name="chevron-right" size={17} color={colors.mutedForeground} /></View><View style={styles.typeRow}><MaterialCommunityIcons name={investigation.type === 'video' ? 'play-circle-outline' : 'image-outline'} size={14} color={colors.mutedForeground} /><Text style={[styles.cardMeta, { color: colors.mutedForeground }]}>{investigation.type === 'video' ? 'Video' : 'Image'} · {investigation.date}</Text></View><View style={styles.badgeRow}><VerdictBadge verdict={investigation.verdict} /><Text style={[styles.smallConfidence, { color: colors.mutedForeground }]}>{investigation.confidence}% match confidence</Text></View></View>
  </Pressable>;
}

export function MetricCard({ icon, label, value, detail, color }: { icon: keyof typeof MaterialCommunityIcons.glyphMap; label: string; value: string; detail?: string; color?: string }) {
  const colors = useColors();
  return <View style={[styles.metricCard, { backgroundColor: colors.card, borderColor: colors.border }]}><View style={[styles.metricIcon, { backgroundColor: `${color ?? colors.primary}1A` }]}><MaterialCommunityIcons name={icon} size={18} color={color ?? colors.primary} /></View><Text style={[styles.metricLabel, { color: colors.mutedForeground }]}>{label}</Text><Text style={[styles.metricValue, { color: colors.foreground }]}>{value}</Text>{detail ? <Text style={[styles.metricDetail, { color: colors.mutedForeground }]}>{detail}</Text> : null}</View>;
}

export function StatCard({ label, value, trend, color }: { label: string; value: string; trend?: string; color?: string }) {
  const colors = useColors();
  return <View style={[styles.statCard, { backgroundColor: colors.card, borderColor: colors.border }]}><Text style={[styles.statLabel, { color: colors.mutedForeground }]}>{label}</Text><Text style={[styles.statValue, { color: colors.foreground }]}>{value}</Text>{trend ? <Text style={[styles.statTrend, { color: color ?? colors.success }]}>{trend}</Text> : null}</View>;
}

export function SourceCard({ source }: { source: SourceMatch }) {
  const colors = useColors();
  const openSource = () => {
    if (source.url) Linking.openURL(source.url).catch(() => undefined);
  };
  return (
    <Pressable onPress={source.url ? openSource : undefined} style={({ pressed }) => [styles.sourceCard, { backgroundColor: colors.card, borderColor: colors.border, opacity: pressed && source.url ? 0.85 : 1 }]}>
      {source.thumbnail ? (
        <Image source={{ uri: source.thumbnail }} style={styles.sourceThumb} />
      ) : (
        <View style={[styles.sourceThumb, styles.sourceThumbPlaceholder, { backgroundColor: colors.surface }]}>
          <Feather name="link" size={18} color={colors.mutedForeground} />
        </View>
      )}
      <View style={styles.sourceBody}>
        <View style={styles.sourceTitleRow}>
          <Text style={[styles.cardTitle, { color: colors.foreground, flex: 1 }]} numberOfLines={2}>{source.title}</Text>
          <Text style={[styles.sourceSimilarity, { color: colors.primary }]}>{source.similarity}%</Text>
        </View>
        <Text style={[styles.cardMeta, { color: colors.mutedForeground }]}>{source.domain}</Text>
        <Text style={[styles.cardMeta, { color: colors.mutedForeground }]}>{source.date} · {source.confidence} confidence</Text>
        <View style={styles.sourceFooterRow}>
          <View style={[styles.matchPill, { backgroundColor: `${colors.primary}14` }]}><Text style={[styles.matchText, { color: colors.primary }]}>{source.match}</Text></View>
          {source.accessible === false ? (
            <Text style={[styles.sourceUnavailable, { color: colors.mutedForeground }]}>Unavailable</Text>
          ) : source.url ? (
            <Feather name="external-link" size={13} color={colors.mutedForeground} />
          ) : null}
        </View>
      </View>
    </Pressable>
  );
}

export function Button({ label, onPress, secondary = false, icon, disabled = false }: { label: string; onPress: () => void; secondary?: boolean; icon?: keyof typeof Feather.glyphMap; disabled?: boolean }) {
  const colors = useColors();
  return <Pressable onPress={onPress} disabled={disabled} style={({ pressed }) => [styles.button, { backgroundColor: secondary ? colors.surface : colors.primary, borderColor: secondary ? colors.border : colors.primary, opacity: disabled ? 0.45 : pressed ? 0.82 : 1 }]}>{icon ? <Feather name={icon} size={17} color={secondary ? colors.foreground : colors.black} /> : null}<Text style={[styles.buttonText, { color: secondary ? colors.foreground : colors.black }]}>{label}</Text></Pressable>;
}

export function LoadingScanner() {
  const colors = useColors();
  const progress = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    Animated.loop(Animated.sequence([Animated.timing(progress, { toValue: 1, duration: 1500, useNativeDriver: true }), Animated.timing(progress, { toValue: 0, duration: 0, useNativeDriver: true })])).start();
  }, [progress]);
  const translateY = progress.interpolate({ inputRange: [0, 1], outputRange: [0, 180] });
  return <View style={[styles.scanner, { backgroundColor: colors.surface, borderColor: colors.border }]}><Image source={{ uri: 'https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?w=800' }} style={styles.scannerImage} /><Animated.View style={[styles.scanLine, { backgroundColor: colors.primary, transform: [{ translateY }] }]} /></View>;
}

export function ProgressRing({ progress, size = 152 }: { progress: number; size?: number }) {
  const colors = useColors();
  return <View style={[styles.ring, { width: size, height: size, borderRadius: size / 2, borderColor: colors.muted }]}><View style={[styles.ringInner, { width: size - 22, height: size - 22, borderRadius: (size - 22) / 2, backgroundColor: colors.card }]}><Text style={[styles.ringValue, { color: colors.foreground }]}>{progress}%</Text><Text style={[styles.ringLabel, { color: colors.mutedForeground }]}>analyzed</Text></View><View style={[styles.ringArc, { borderColor: colors.primary, width: size, height: size, borderRadius: size / 2, transform: [{ rotate: `${progress * 3.6 - 45}deg` }] }]} /></View>;
}

export function EmptyState({ title, description, icon = 'folder' }: { title: string; description: string; icon?: keyof typeof Feather.glyphMap }) {
  const colors = useColors();
  return <View style={styles.empty}><View style={[styles.emptyIcon, { backgroundColor: colors.surface }]}><Feather name={icon} size={25} color={colors.primary} /></View><Text style={[styles.emptyTitle, { color: colors.foreground }]}>{title}</Text><Text style={[styles.emptyDescription, { color: colors.mutedForeground }]}>{description}</Text></View>;
}

export function ErrorState({ title, description, onRetry }: { title: string; description: string; onRetry?: () => void }) {
  const colors = useColors();
  return <View style={styles.empty}><View style={[styles.emptyIcon, { backgroundColor: `${colors.destructive}18` }]}><Feather name="alert-circle" size={25} color={colors.destructive} /></View><Text style={[styles.emptyTitle, { color: colors.foreground }]}>{title}</Text><Text style={[styles.emptyDescription, { color: colors.mutedForeground }]}>{description}</Text>{onRetry ? <Pressable onPress={onRetry} style={[styles.retry, { backgroundColor: colors.surface }]}><Text style={[styles.retryText, { color: colors.primary }]}>Try again</Text></Pressable> : null}</View>;
}

export function MiniBarChart({ values, labels }: { values?: number[]; labels?: string[] } = {}) {
  const colors = useColors();
  const data = values && values.length ? values : [34, 62, 48, 84, 58, 72, 94];
  const dayLabels = labels && labels.length === data.length ? labels : ['M', 'T', 'W', 'T', 'F', 'S', 'S'];
  const max = Math.max(1, ...data);
  const bars = data.map((value) => Math.max(4, Math.round((value / max) * 94)));
  return <View style={styles.chart}>{bars.map((height, index) => <View key={index} style={styles.barWrap}><View style={[styles.bar, { height, backgroundColor: index === bars.length - 1 ? colors.primary : `${colors.primary}55` }]} /><Text style={[styles.chartLabel, { color: colors.mutedForeground }]}>{dayLabels[index]}</Text></View>)}</View>;
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  scrollContent: { padding: 20, paddingBottom: 115 },
  logo: { alignItems: 'center', justifyContent: 'center' },
  header: { flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 25 },
  headerCopy: { flex: 1 },
  headerTitle: { fontSize: 22, fontFamily: 'Inter_700Bold', letterSpacing: -0.4 },
  headerSubtitle: { fontSize: 12, fontFamily: 'Inter_400Regular', marginTop: 3 },
  headerSpacer: { width: 35 },
  iconButton: { width: 38, height: 38, borderRadius: 13, alignItems: 'center', justifyContent: 'center' },
  sectionHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 27, marginBottom: 13 },
  sectionTitle: { fontSize: 16, fontFamily: 'Inter_600SemiBold' },
  sectionAction: { fontSize: 12, fontFamily: 'Inter_600SemiBold' },
  caption: { fontSize: 11, fontFamily: 'Inter_500Medium' },
  button: { minHeight: 54, paddingHorizontal: 20, borderRadius: 17, borderWidth: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 9 },
  buttonText: { fontSize: 14, fontFamily: 'Inter_700Bold' },
  investigationCard: { flexDirection: 'row', padding: 10, borderRadius: 18, borderWidth: 1, marginBottom: 10 },
  thumb: { width: 71, height: 71, borderRadius: 13, backgroundColor: '#202B37' },
  cardMain: { flex: 1, paddingLeft: 12, justifyContent: 'space-around' },
  fileRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 4 },
  cardTitle: { fontSize: 13, fontFamily: 'Inter_600SemiBold' },
  typeRow: { flexDirection: 'row', alignItems: 'center', gap: 5 },
  cardMeta: { fontSize: 10, fontFamily: 'Inter_400Regular' },
  badgeRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  verdictBadge: { flexDirection: 'row', alignItems: 'center', paddingVertical: 5, paddingHorizontal: 7, borderRadius: 8, gap: 4, alignSelf: 'flex-start' },
  verdictText: { fontSize: 9, fontFamily: 'Inter_600SemiBold' },
  smallConfidence: { fontSize: 9, fontFamily: 'Inter_400Regular' },
  confidence: { gap: 8 },
  confidenceCompact: { gap: 6, marginTop: 8 },
  confidenceRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  confidenceValue: { fontSize: 12, fontFamily: 'Inter_700Bold' },
  progressTrack: { height: 5, borderRadius: 5, overflow: 'hidden' },
  progressFill: { height: '100%', borderRadius: 5 },
  metricCard: { width: '48.5%', padding: 14, borderRadius: 17, borderWidth: 1, marginBottom: 10 },
  metricIcon: { width: 34, height: 34, borderRadius: 11, alignItems: 'center', justifyContent: 'center', marginBottom: 11 },
  metricLabel: { fontSize: 10, fontFamily: 'Inter_500Medium' },
  metricValue: { fontSize: 18, fontFamily: 'Inter_700Bold', marginTop: 3 },
  metricDetail: { fontSize: 10, fontFamily: 'Inter_400Regular', marginTop: 2 },
  statCard: { width: '48.5%', minHeight: 95, padding: 14, borderRadius: 17, borderWidth: 1, marginBottom: 10 },
  statLabel: { fontSize: 10, fontFamily: 'Inter_500Medium' },
  statValue: { fontSize: 25, fontFamily: 'Inter_700Bold', marginTop: 8 },
  statTrend: { fontSize: 10, fontFamily: 'Inter_600SemiBold', marginTop: 2 },
  sourceCard: { flexDirection: 'row', padding: 10, borderRadius: 17, borderWidth: 1, marginBottom: 10 },
  sourceThumb: { width: 76, height: 89, borderRadius: 12 },
  sourceThumbPlaceholder: { alignItems: 'center', justifyContent: 'center' },
  sourceBody: { flex: 1, paddingLeft: 11, gap: 5 },
  sourceTitleRow: { flexDirection: 'row', gap: 5 },
  sourceFooterRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 1 },
  sourceUnavailable: { fontSize: 9, fontFamily: 'Inter_500Medium' },
  sourceSimilarity: { fontSize: 13, fontFamily: 'Inter_700Bold' },
  matchPill: { alignSelf: 'flex-start', paddingVertical: 4, paddingHorizontal: 7, borderRadius: 7, marginTop: 1 },
  matchText: { fontSize: 9, fontFamily: 'Inter_600SemiBold' },
  scanner: { height: 205, borderRadius: 22, overflow: 'hidden', borderWidth: 1, position: 'relative' },
  scannerImage: { width: '100%', height: '100%', opacity: 0.68 },
  scanLine: { position: 'absolute', top: 0, left: 12, right: 12, height: 2 },
  ring: { alignItems: 'center', justifyContent: 'center', position: 'relative', borderWidth: 9 },
  ringInner: { alignItems: 'center', justifyContent: 'center' },
  ringValue: { fontSize: 30, fontFamily: 'Inter_700Bold' },
  ringLabel: { fontSize: 11, fontFamily: 'Inter_500Medium', marginTop: 2 },
  ringArc: { position: 'absolute', borderWidth: 9, borderLeftColor: 'transparent', borderBottomColor: 'transparent' },
  empty: { alignItems: 'center', paddingHorizontal: 28, paddingVertical: 58 },
  emptyIcon: { width: 58, height: 58, borderRadius: 20, alignItems: 'center', justifyContent: 'center', marginBottom: 16 },
  emptyTitle: { fontSize: 16, fontFamily: 'Inter_600SemiBold' },
  emptyDescription: { textAlign: 'center', fontSize: 12, lineHeight: 18, fontFamily: 'Inter_400Regular', marginTop: 7 },
  retry: { paddingHorizontal: 15, paddingVertical: 10, borderRadius: 11, marginTop: 16 },
  retryText: { fontSize: 11, fontFamily: 'Inter_700Bold' },
  chart: { height: 128, flexDirection: 'row', alignItems: 'flex-end', justifyContent: 'space-between', paddingTop: 10 },
  barWrap: { height: 118, alignItems: 'center', justifyContent: 'flex-end', gap: 8 },
  bar: { width: 21, borderRadius: 7 },
  chartLabel: { fontSize: 9, fontFamily: 'Inter_500Medium' },
});