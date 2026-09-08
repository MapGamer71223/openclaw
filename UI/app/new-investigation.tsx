import React, { useState } from 'react';
import { ActivityIndicator, Alert, Image, Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { router } from 'expo-router';
import * as ImagePicker from 'expo-image-picker';
import { Feather, MaterialCommunityIcons } from '@expo/vector-icons';
import { useColors } from '@/hooks/useColors';
import { useInvestigations } from '@/context/InvestigationContext';
import { Button, Header, ScrollScreen } from '@/components/ui';
import { createInvestigation, seedDemoInvestigation, startInvestigation } from '@/services/investigationService';
import { ApiError, UploadFileInput } from '@/services/api';
import { MediaType } from '@/types/investigation';

interface SelectedMedia {
  uri: string;
  filename: string;
  type: MediaType;
  size: string;
  resolution: string;
  mimeType: string;
}

function guessMimeType(filename: string, type: MediaType): string {
  const ext = filename.split('.').pop()?.toLowerCase();
  if (type === 'video') return ext === 'mov' ? 'video/quicktime' : 'video/mp4';
  if (ext === 'png') return 'image/png';
  if (ext === 'webp') return 'image/webp';
  return 'image/jpeg';
}

export default function NewInvestigationScreen() {
  const colors = useColors();
  const { setCurrent, addInvestigation } = useInvestigations();
  const [media, setMedia] = useState<SelectedMedia | null>(null);
  const [mode, setMode] = useState<'quick' | 'deep'>('deep');
  const [busy, setBusy] = useState<null | 'uploading' | 'starting' | 'demo'>(null);
  const [error, setError] = useState<string | null>(null);

  const pickMedia = async (camera = false) => {
    setError(null);
    if (camera && Platform.OS !== 'web') {
      const permission = await ImagePicker.requestCameraPermissionsAsync();
      if (!permission.granted) {
        Alert.alert('Camera access needed', 'Allow camera access in Settings, or use "Use demo image" below instead.');
        return;
      }
    } else {
      const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (!permission.granted) {
        Alert.alert('Photo library access needed', 'Allow photo library access in Settings, or use "Use demo image" below instead.');
        return;
      }
    }
    const result = camera
      ? await ImagePicker.launchCameraAsync({ mediaTypes: ['images', 'videos'], quality: 0.85 })
      : await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images', 'videos'], quality: 0.85 });
    if (!result.canceled) {
      const asset = result.assets[0];
      const type: MediaType = asset.type === 'video' ? 'video' : 'image';
      const filename = asset.fileName ?? (type === 'video' ? 'captured-video.mp4' : 'captured-image.jpg');
      setMedia({
        uri: asset.uri,
        filename,
        type,
        size: asset.fileSize ? `${(asset.fileSize / 1024 / 1024).toFixed(1)} MB` : 'Unknown size',
        resolution: asset.width && asset.height ? `${asset.width} × ${asset.height}` : 'Unknown resolution',
        mimeType: asset.mimeType ?? guessMimeType(filename, type),
      });
    }
  };

  const runDemo = async () => {
    setError(null);
    setBusy('demo');
    try {
      const item = await seedDemoInvestigation();
      setCurrent(item);
      addInvestigation(item);
      router.push({ pathname: '/progress', params: { id: item.id } });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not reach the JanSatark AI backend to run the demo investigation.');
    } finally {
      setBusy(null);
    }
  };

  const start = async () => {
    if (!media) {
      // No file selected -- offer the server-side demo pipeline instead of
      // silently fabricating a fake upload.
      await runDemo();
      return;
    }
    setError(null);
    try {
      setBusy('uploading');
      const uploadInput: UploadFileInput = { uri: media.uri, name: media.filename, mimeType: media.mimeType };
      const created = await createInvestigation(uploadInput);
      setBusy('starting');
      const started = await startInvestigation(created.id, mode);
      setCurrent(started);
      addInvestigation(started);
      router.push({ pathname: '/progress', params: { id: started.id } });
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : 'Something went wrong starting the investigation. Check your connection and try again.',
      );
    } finally {
      setBusy(null);
    }
  };

  const isBusy = busy !== null;

  return (
    <ScrollScreen>
      <Header title="New investigation" subtitle="Add evidence to begin" onBack={() => router.back()} />
      <Text style={[styles.intro, { color: colors.mutedForeground }]}>
        Upload a piece of media and let JanSatark AI inspect its origin, integrity, and digital fingerprints.
      </Text>
      {media ? (
        <View style={[styles.previewCard, { backgroundColor: colors.card, borderColor: colors.border }]}>
          <Image source={{ uri: media.uri }} style={styles.preview} />
          <View style={styles.mediaInfo}>
            <View style={styles.mediaTitleRow}>
              <Text style={[styles.mediaName, { color: colors.foreground }]} numberOfLines={1}>{media.filename}</Text>
              <Pressable onPress={() => setMedia(null)} disabled={isBusy}>
                <Feather name="x-circle" size={18} color={colors.mutedForeground} />
              </Pressable>
            </View>
            <Text style={[styles.mediaMeta, { color: colors.mutedForeground }]}>
              {media.type === 'video' ? 'Video' : 'Image'} · {media.size} · {media.resolution}
            </Text>
          </View>
        </View>
      ) : (
        <Pressable
          onPress={runDemo}
          disabled={isBusy}
          style={[styles.upload, { backgroundColor: colors.card, borderColor: `${colors.primary}60`, opacity: isBusy ? 0.6 : 1 }]}
        >
          <View style={[styles.uploadIcon, { backgroundColor: `${colors.primary}18` }]}>
            {busy === 'demo' ? <ActivityIndicator color={colors.primary} /> : <Feather name="upload-cloud" size={26} color={colors.primary} />}
          </View>
          <Text style={[styles.uploadTitle, { color: colors.foreground }]}>Drop your evidence here</Text>
          <Text style={[styles.uploadDetail, { color: colors.mutedForeground }]}>JPG, PNG, WEBP, MP4 up to 100 MB</Text>
          <Text style={[styles.demoHint, { color: colors.primary }]}>Tap to run the demo pipeline instead</Text>
        </Pressable>
      )}
      <View style={styles.actionRow}>
        <Pressable onPress={() => pickMedia(true)} disabled={isBusy} style={[styles.action, { backgroundColor: colors.surface, borderColor: colors.border, opacity: isBusy ? 0.6 : 1 }]}>
          <Feather name="camera" size={18} color={colors.primary} />
          <Text style={[styles.actionText, { color: colors.foreground }]}>Take photo</Text>
        </Pressable>
        <Pressable onPress={() => pickMedia(false)} disabled={isBusy} style={[styles.action, { backgroundColor: colors.surface, borderColor: colors.border, opacity: isBusy ? 0.6 : 1 }]}>
          <Feather name="image" size={18} color={colors.accent} />
          <Text style={[styles.actionText, { color: colors.foreground }]}>Choose gallery</Text>
        </Pressable>
      </View>
      <Text style={[styles.modeLabel, { color: colors.foreground }]}>Investigation mode</Text>
      <Pressable
        onPress={() => setMode('quick')}
        disabled={isBusy}
        style={[styles.mode, { backgroundColor: mode === 'quick' ? `${colors.primary}12` : colors.card, borderColor: mode === 'quick' ? colors.primary : colors.border }]}
      >
        <View style={[styles.radio, { borderColor: mode === 'quick' ? colors.primary : colors.mutedForeground }]}>
          {mode === 'quick' ? <View style={[styles.radioDot, { backgroundColor: colors.primary }]} /> : null}
        </View>
        <View style={styles.modeCopy}>
          <Text style={[styles.modeTitle, { color: colors.foreground }]}>Quick scan</Text>
          <Text style={[styles.modeDetail, { color: colors.mutedForeground }]}>AI detection only, then origin search if AI-generated</Text>
        </View>
        <MaterialCommunityIcons name="lightning-bolt-outline" size={20} color={colors.warning} />
      </Pressable>
      <Pressable
        onPress={() => setMode('deep')}
        disabled={isBusy}
        style={[styles.mode, { backgroundColor: mode === 'deep' ? `${colors.accent}12` : colors.card, borderColor: mode === 'deep' ? colors.accent : colors.border }]}
      >
        <View style={[styles.radio, { borderColor: mode === 'deep' ? colors.accent : colors.mutedForeground }]}>
          {mode === 'deep' ? <View style={[styles.radioDot, { backgroundColor: colors.accent }]} /> : null}
        </View>
        <View style={styles.modeCopy}>
          <View style={styles.modeTitleRow}>
            <Text style={[styles.modeTitle, { color: colors.foreground }]}>Deep investigation</Text>
            <Text style={[styles.recommended, { color: colors.accent, backgroundColor: `${colors.accent}18` }]}>RECOMMENDED</Text>
          </View>
          <Text style={[styles.modeDetail, { color: colors.mutedForeground }]}>Full forensic pipeline: metadata, forensics, sources, propagation</Text>
        </View>
        <MaterialCommunityIcons name="shield-alert-outline" size={20} color={colors.accent} />
      </Pressable>
      {error ? (
        <View style={[styles.errorBox, { backgroundColor: `${colors.destructive}14`, borderColor: `${colors.destructive}45` }]}>
          <Feather name="alert-circle" size={16} color={colors.destructive} />
          <Text style={[styles.errorText, { color: colors.destructive }]}>{error}</Text>
        </View>
      ) : null}
      <View style={styles.bottom}>
        <Button
          label={busy === 'uploading' ? 'Uploading evidence…' : busy === 'starting' ? 'Starting investigation…' : busy === 'demo' ? 'Running demo pipeline…' : media ? 'Start investigation' : 'Use demo & investigate'}
          onPress={start}
          icon={isBusy ? undefined : 'arrow-right'}
          disabled={isBusy}
        />
      </View>
    </ScrollScreen>
  );
}

const styles = StyleSheet.create({
  intro: { fontSize: 13, lineHeight: 19, fontFamily: 'Inter_400Regular', marginBottom: 20 },
  upload: { height: 224, borderRadius: 22, borderWidth: 1, borderStyle: 'dashed', alignItems: 'center', justifyContent: 'center' },
  uploadIcon: { width: 58, height: 58, borderRadius: 20, alignItems: 'center', justifyContent: 'center', marginBottom: 14 },
  uploadTitle: { fontSize: 14, fontFamily: 'Inter_700Bold' },
  uploadDetail: { fontSize: 10, fontFamily: 'Inter_400Regular', marginTop: 7 },
  demoHint: { fontSize: 10, fontFamily: 'Inter_600SemiBold', marginTop: 17 },
  actionRow: { flexDirection: 'row', gap: 10, marginTop: 12 },
  action: { flex: 1, minHeight: 52, borderRadius: 15, borderWidth: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8 },
  actionText: { fontSize: 11, fontFamily: 'Inter_600SemiBold' },
  previewCard: { padding: 11, borderRadius: 20, borderWidth: 1 },
  preview: { width: '100%', height: 200, borderRadius: 13 },
  mediaInfo: { paddingTop: 12, paddingHorizontal: 2 },
  mediaTitleRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 },
  mediaName: { flex: 1, fontSize: 13, fontFamily: 'Inter_700Bold' },
  mediaMeta: { fontSize: 10, fontFamily: 'Inter_400Regular', marginTop: 5 },
  modeLabel: { fontSize: 14, fontFamily: 'Inter_700Bold', marginTop: 26, marginBottom: 11 },
  mode: { flexDirection: 'row', alignItems: 'center', padding: 15, borderRadius: 17, borderWidth: 1, marginBottom: 10, gap: 12 },
  radio: { width: 18, height: 18, borderRadius: 10, borderWidth: 1.5, alignItems: 'center', justifyContent: 'center' },
  radioDot: { width: 9, height: 9, borderRadius: 5 },
  modeCopy: { flex: 1 },
  modeTitleRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  modeTitle: { fontSize: 12, fontFamily: 'Inter_700Bold' },
  modeDetail: { fontSize: 10, fontFamily: 'Inter_400Regular', marginTop: 4 },
  recommended: { fontSize: 7, fontFamily: 'Inter_700Bold', paddingHorizontal: 6, paddingVertical: 4, borderRadius: 5 },
  errorBox: { flexDirection: 'row', alignItems: 'flex-start', gap: 8, borderRadius: 14, borderWidth: 1, padding: 12, marginTop: 16 },
  errorText: { flex: 1, fontSize: 11, lineHeight: 16, fontFamily: 'Inter_500Medium' },
  bottom: { marginTop: 12, marginBottom: 3 },
});
