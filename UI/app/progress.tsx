import React, { useEffect, useRef, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { router, useLocalSearchParams } from 'expo-router';
import { Feather, MaterialCommunityIcons } from '@expo/vector-icons';
import { useColors } from '@/hooks/useColors';
import { useInvestigations } from '@/context/InvestigationContext';
import { getInvestigationStatus, startInvestigation } from '@/services/investigationService';
import { Button, Header, LoadingScanner, ProgressRing, ScrollScreen } from '@/components/ui';
import { BackendEvent, ProgressItem, STAGE_LABELS, STAGE_ORDER, STAGE_PROGRESS } from '@/types/investigation';
import { ApiError } from '@/services/api';

const POLL_INTERVAL_MS = 1500;

function relativeTime(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const seconds = Math.max(0, Math.round(diffMs / 1000));
  if (seconds < 3) return 'now';
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.round(seconds / 60);
  return `${minutes}m ago`;
}

function buildSteps(currentStage: string | null, terminalState: string): ProgressItem[] {
  const currentIndex = currentStage ? STAGE_ORDER.indexOf(currentStage as (typeof STAGE_ORDER)[number]) : -1;
  return STAGE_ORDER.map((stage, index) => {
    let status: ProgressItem['status'] = 'pending';
    if (terminalState === 'COMPLETED' || terminalState === 'PARTIAL') status = 'completed';
    else if (index < currentIndex) status = 'completed';
    else if (index === currentIndex) status = 'active';
    return { label: STAGE_LABELS[stage], detail: status === 'completed' ? 'Done' : status === 'active' ? 'In progress' : 'Waiting', status, stage };
  });
}

export default function ProgressScreen() {
  const colors = useColors();
  const params = useLocalSearchParams<{ id?: string }>();
  const { current, setCurrent } = useInvestigations();
  const id = params.id ?? current?.id;

  const [progress, setProgress] = useState(0);
  const [events, setEvents] = useState<BackendEvent[]>([]);
  const [state, setState] = useState<string>('UPLOADED');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [connectionIssue, setConnectionIssue] = useState<string | null>(null);
  const [retrying, setRetrying] = useState(false);
  const navigatedRef = useRef(false);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    let timer: ReturnType<typeof setInterval> | null = null;

    const poll = async () => {
      try {
        const status = await getInvestigationStatus(id);
        if (cancelled) return;
        setConnectionIssue(null);
        setState(status.state);
        setErrorMessage(status.error_message);
        setEvents(status.events);
        const latestStage = [...status.events].reverse().find((e) => e.stage)?.stage ?? null;
        const pct = status.state === 'COMPLETED' || status.state === 'PARTIAL' ? 100 : (latestStage && STAGE_PROGRESS[latestStage]) || 5;
        setProgress(pct);

        const terminal = status.state === 'COMPLETED' || status.state === 'FAILED' || status.state === 'PARTIAL';
        if (terminal && timer) {
          clearInterval(timer);
          timer = null;
        }
        if ((status.state === 'COMPLETED' || status.state === 'PARTIAL') && !navigatedRef.current) {
          navigatedRef.current = true;
          setTimeout(() => {
            if (!cancelled) router.replace({ pathname: '/results', params: { id } });
          }, 450);
        }
      } catch (err) {
        if (!cancelled) {
          setConnectionIssue(err instanceof ApiError ? err.message : 'Lost connection to the backend. Retrying…');
        }
      }
    };

    poll();
    timer = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      if (timer) clearInterval(timer);
    };
  }, [id]);

  const retryInvestigation = async () => {
    if (!id) return;
    setRetrying(true);
    try {
      const started = await startInvestigation(id, 'deep');
      setCurrent(started);
      navigatedRef.current = false;
      setState('UPLOADED');
      setErrorMessage(null);
    } catch (err) {
      setConnectionIssue(err instanceof ApiError ? err.message : 'Could not restart the investigation.');
    } finally {
      setRetrying(false);
    }
  };

  if (!id) {
    return (
      <ScrollScreen>
        <Header title="Investigation in progress" onBack={() => router.back()} />
        <Text style={{ color: colors.foreground }}>No investigation selected.</Text>
      </ScrollScreen>
    );
  }

  const steps = buildSteps([...events].reverse().find((e) => e.stage)?.stage ?? null, state);
  const statusColor = (status: ProgressItem['status']) => (status === 'completed' ? colors.success : status === 'active' ? colors.primary : colors.mutedForeground);
  const feed = [...events].reverse().slice(0, 6);

  if (state === 'FAILED') {
    return (
      <ScrollScreen>
        <Header title="Investigation failed" subtitle={current?.filename} onBack={() => router.back()} />
        <View style={[styles.failureCard, { backgroundColor: `${colors.destructive}12`, borderColor: `${colors.destructive}45` }]}>
          <MaterialCommunityIcons name="alert-circle-outline" size={32} color={colors.destructive} />
          <Text style={[styles.failureTitle, { color: colors.foreground }]}>The investigation could not complete</Text>
          <Text style={[styles.failureDetail, { color: colors.mutedForeground }]}>{errorMessage ?? 'An unexpected error occurred while processing this evidence.'}</Text>
        </View>
        <View style={styles.bottom}>
          <Button label={retrying ? 'Retrying…' : 'Retry investigation'} onPress={retryInvestigation} disabled={retrying} icon="refresh-cw" />
        </View>
      </ScrollScreen>
    );
  }

  return (
    <ScrollScreen>
      <Header title="Investigation in progress" subtitle={`${current?.rawState === 'UPLOADED' ? 'Starting' : 'Running'} · ${state.replace(/_/g, ' ')}`} onBack={() => router.back()} />
      <LoadingScanner />
      <View style={styles.progressTop}>
        <ProgressRing progress={progress} />
        <View style={styles.progressCopy}>
          <Text style={[styles.running, { color: colors.primary }]}>ANALYZING EVIDENCE</Text>
          <Text style={[styles.file, { color: colors.foreground }]} numberOfLines={2}>{current?.filename ?? 'Uploaded media'}</Text>
          <Text style={[styles.detail, { color: colors.mutedForeground }]}>Our agents are checking every signal across the media file.</Text>
        </View>
      </View>
      {connectionIssue ? (
        <View style={[styles.connectionBanner, { backgroundColor: `${colors.warning}18` }]}>
          <Feather name="wifi-off" size={14} color={colors.warning} />
          <Text style={[styles.connectionText, { color: colors.warning }]}>{connectionIssue}</Text>
        </View>
      ) : null}
      <Text style={[styles.pipelineTitle, { color: colors.foreground }]}>Analysis pipeline</Text>
      <View style={[styles.pipeline, { backgroundColor: colors.card, borderColor: colors.border }]}>
        {steps.map((step, index) => (
          <View key={step.label} style={styles.step}>
            <View style={styles.stepRail}>
              {index < steps.length - 1 ? <View style={[styles.rail, { backgroundColor: step.status === 'completed' ? colors.success : colors.muted }]} /> : null}
              <View style={[styles.stepDot, { backgroundColor: `${statusColor(step.status)}22`, borderColor: statusColor(step.status) }]}>
                {step.status === 'completed' ? (
                  <MaterialCommunityIcons name="check" size={12} color={colors.success} />
                ) : step.status === 'active' ? (
                  <View style={[styles.activeDot, { backgroundColor: colors.primary }]} />
                ) : null}
              </View>
            </View>
            <View style={styles.stepCopy}>
              <Text style={[styles.stepLabel, { color: colors.foreground }]}>{step.label}</Text>
              <Text style={[styles.stepDetail, { color: statusColor(step.status) }]}>{step.detail}</Text>
            </View>
          </View>
        ))}
      </View>
      <Text style={[styles.feedTitle, { color: colors.foreground }]}>Live investigation feed</Text>
      <View style={styles.feed}>
        {feed.length ? (
          feed.map((event, index) => (
            <View key={`${event.timestamp}-${index}`} style={styles.feedRow}>
              <View style={[styles.feedDot, { backgroundColor: index === 0 ? colors.primary : colors.success }]} />
              <Text style={[styles.feedText, { color: colors.mutedForeground }]} numberOfLines={1}>{event.action}</Text>
              <Text style={[styles.feedTime, { color: colors.mutedForeground }]}>{relativeTime(event.timestamp)}</Text>
            </View>
          ))
        ) : (
          <Text style={[styles.feedText, { color: colors.mutedForeground }]}>Waiting for the first agent update…</Text>
        )}
      </View>
    </ScrollScreen>
  );
}

const styles = StyleSheet.create({
  progressTop: { flexDirection: 'row', alignItems: 'center', gap: 20, marginTop: 22 },
  progressCopy: { flex: 1 },
  running: { fontSize: 9, fontFamily: 'Inter_700Bold', letterSpacing: 1.2 },
  file: { fontSize: 14, lineHeight: 19, fontFamily: 'Inter_700Bold', marginTop: 9 },
  detail: { fontSize: 11, lineHeight: 16, fontFamily: 'Inter_400Regular', marginTop: 8 },
  connectionBanner: { flexDirection: 'row', alignItems: 'center', gap: 8, borderRadius: 12, padding: 10, marginTop: 14 },
  connectionText: { flex: 1, fontSize: 10, fontFamily: 'Inter_500Medium' },
  pipelineTitle: { fontSize: 15, fontFamily: 'Inter_700Bold', marginTop: 30, marginBottom: 12 },
  pipeline: { borderRadius: 19, borderWidth: 1, padding: 17 },
  step: { flexDirection: 'row', minHeight: 49 },
  stepRail: { width: 26, alignItems: 'center', position: 'relative' },
  rail: { position: 'absolute', top: 22, bottom: -8, width: 1 },
  stepDot: { width: 21, height: 21, borderRadius: 11, borderWidth: 1, alignItems: 'center', justifyContent: 'center', zIndex: 1 },
  activeDot: { width: 7, height: 7, borderRadius: 4 },
  stepCopy: { paddingLeft: 10, paddingBottom: 13 },
  stepLabel: { fontSize: 11, fontFamily: 'Inter_600SemiBold' },
  stepDetail: { fontSize: 10, fontFamily: 'Inter_400Regular', marginTop: 3 },
  feedTitle: { fontSize: 15, fontFamily: 'Inter_700Bold', marginTop: 28, marginBottom: 11 },
  feed: { gap: 12, paddingBottom: 20 },
  feedRow: { flexDirection: 'row', alignItems: 'center', gap: 9 },
  feedDot: { width: 6, height: 6, borderRadius: 3 },
  feedText: { flex: 1, fontSize: 11, fontFamily: 'Inter_400Regular' },
  feedTime: { fontSize: 9, fontFamily: 'Inter_400Regular' },
  failureCard: { borderRadius: 22, borderWidth: 1, padding: 24, alignItems: 'center', marginTop: 20, gap: 10 },
  failureTitle: { fontSize: 15, fontFamily: 'Inter_700Bold', textAlign: 'center' },
  failureDetail: { fontSize: 12, lineHeight: 18, fontFamily: 'Inter_400Regular', textAlign: 'center' },
  bottom: { marginTop: 24, marginBottom: 3 },
});
