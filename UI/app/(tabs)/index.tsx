import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { router } from 'expo-router';
import { Feather, MaterialCommunityIcons } from '@expo/vector-icons';
import { useColors } from '@/hooks/useColors';
import { useInvestigations } from '@/context/InvestigationContext';
import { InvestigationCard, LogoMark, ScrollScreen, SectionHeader } from '@/components/ui';

const capabilities = [
  { icon: 'creation' as const, label: 'AI Detection', color: '#EF4444' },
  { icon: 'scan-helper' as const, label: 'Forensics', color: '#7C5CFC' },
  { icon: 'compass-outline' as const, label: 'Origin Trace', color: '#00D4FF' },
  { icon: 'file-search-outline' as const, label: 'Metadata', color: '#22C55E' },
  { icon: 'graph-outline' as const, label: 'Propagation', color: '#F59E0B' },
];

export default function HomeScreen() {
  const colors = useColors();
  const { investigations, setCurrent } = useInvestigations();
  return <ScrollScreen>
    <View style={styles.top}><View><Text style={[styles.eyebrow, { color: colors.primary }]}>WEDNESDAY, SEPT 02</Text><Text style={[styles.greeting, { color: colors.foreground }]}>Good morning, Alex</Text></View><Pressable style={[styles.notify, { backgroundColor: colors.surface }]}><Feather name="bell" size={19} color={colors.foreground} /><View style={[styles.dot, { backgroundColor: colors.primary }]} /></Pressable></View>
    <View style={[styles.hero, { backgroundColor: colors.card, borderColor: colors.border }]}><View style={styles.heroGlow} /><View style={styles.heroCopy}><View style={[styles.heroTag, { backgroundColor: `${colors.primary}16` }]}><MaterialCommunityIcons name="shield-check-outline" size={14} color={colors.primary} /><Text style={[styles.heroTagText, { color: colors.primary }]}>ANALYSIS ENGINE READY</Text></View><Text style={[styles.heroTitle, { color: colors.foreground }]}>Investigate{'\n'}digital media.</Text><Text style={[styles.heroDescription, { color: colors.mutedForeground }]}>Uncover the truth behind images and videos with AI-powered forensics.</Text><Pressable onPress={() => router.push('/new-investigation')} style={({ pressed }) => [styles.heroButton, { backgroundColor: colors.primary, opacity: pressed ? 0.8 : 1 }]}><Text style={[styles.heroButtonText, { color: colors.black }]}>Start investigation</Text><Feather name="arrow-up-right" size={17} color={colors.black} /></Pressable></View><View style={styles.heroVisual}><LogoMark small /><View style={[styles.orbit, styles.orbitOne, { borderColor: `${colors.primary}55` }]} /><View style={[styles.orbit, styles.orbitTwo, { borderColor: `${colors.accent}55` }]} /></View></View>
    <SectionHeader title="Quick actions" />
    <View style={styles.quickRow}><Pressable onPress={() => router.push('/new-investigation')} style={[styles.quick, { backgroundColor: colors.surface, borderColor: colors.border }]}><View style={[styles.quickIcon, { backgroundColor: `${colors.primary}18` }]}><Feather name="image" size={19} color={colors.primary} /></View><Text style={[styles.quickText, { color: colors.foreground }]}>Scan image</Text></Pressable><Pressable onPress={() => router.push('/new-investigation')} style={[styles.quick, { backgroundColor: colors.surface, borderColor: colors.border }]}><View style={[styles.quickIcon, { backgroundColor: `${colors.accent}18` }]}><Feather name="video" size={19} color={colors.accent} /></View><Text style={[styles.quickText, { color: colors.foreground }]}>Scan video</Text></Pressable></View>
    <SectionHeader title="Analysis capabilities" />
    <View style={styles.capabilityRow}>{capabilities.map((item) => <View key={item.label} style={[styles.capability, { backgroundColor: colors.card, borderColor: colors.border }]}><View style={[styles.capabilityIcon, { backgroundColor: `${item.color}18` }]}><MaterialCommunityIcons name={item.icon} size={20} color={item.color} /></View><Text style={[styles.capabilityText, { color: colors.foreground }]}>{item.label}</Text></View>)}</View>
    <SectionHeader title="Recent investigations" action="View all" onAction={() => router.push('/(tabs)/investigations')} />
    {investigations.slice(0, 3).map((item) => <InvestigationCard key={item.id} investigation={item} onPress={() => { setCurrent(item); router.push(item.status === 'processing' ? { pathname: '/progress', params: { id: item.id } } : { pathname: '/results', params: { id: item.id } }); }} />)}
    {!investigations.length ? <Text style={[styles.noRecent, { color: colors.mutedForeground }]}>Your completed scans will appear here.</Text> : null}
  </ScrollScreen>;
}

const styles = StyleSheet.create({
  top: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 22 },
  eyebrow: { fontSize: 10, fontFamily: 'Inter_700Bold', letterSpacing: 1.5 },
  greeting: { fontSize: 22, fontFamily: 'Inter_700Bold', marginTop: 5, letterSpacing: -0.5 },
  notify: { width: 42, height: 42, borderRadius: 15, alignItems: 'center', justifyContent: 'center' },
  dot: { width: 6, height: 6, borderRadius: 4, position: 'absolute', top: 10, right: 10 },
  hero: { minHeight: 280, padding: 22, borderRadius: 25, borderWidth: 1, overflow: 'hidden', flexDirection: 'row' },
  heroCopy: { flex: 1, zIndex: 2 },
  heroGlow: { position: 'absolute', width: 190, height: 190, borderRadius: 100, right: -75, top: -55, backgroundColor: '#00D4FF12' },
  heroTag: { alignSelf: 'flex-start', flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 8, paddingVertical: 6, borderRadius: 8 },
  heroTagText: { fontSize: 8, fontFamily: 'Inter_700Bold', letterSpacing: 0.6 },
  heroTitle: { fontSize: 31, lineHeight: 34, fontFamily: 'Inter_700Bold', letterSpacing: -1.1, marginTop: 18 },
  heroDescription: { maxWidth: 218, fontSize: 12, lineHeight: 18, fontFamily: 'Inter_400Regular', marginTop: 12 },
  heroButton: { alignSelf: 'flex-start', flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 13, paddingVertical: 11, borderRadius: 12, marginTop: 19 },
  heroButtonText: { fontSize: 11, fontFamily: 'Inter_700Bold' },
  heroVisual: { width: 64, alignItems: 'center', justifyContent: 'center', position: 'relative' },
  orbit: { position: 'absolute', borderWidth: 1, borderRadius: 100 },
  orbitOne: { width: 104, height: 104 },
  orbitTwo: { width: 142, height: 142 },
  quickRow: { flexDirection: 'row', gap: 10 },
  quick: { flex: 1, padding: 13, borderRadius: 17, borderWidth: 1, flexDirection: 'row', alignItems: 'center', gap: 9 },
  quickIcon: { width: 36, height: 36, borderRadius: 11, alignItems: 'center', justifyContent: 'center' },
  quickText: { fontSize: 12, fontFamily: 'Inter_600SemiBold' },
  capabilityRow: { flexDirection: 'row', gap: 9 },
  capability: { width: 91, height: 92, borderWidth: 1, borderRadius: 16, padding: 10, justifyContent: 'space-between' },
  capabilityIcon: { width: 33, height: 33, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
  capabilityText: { fontSize: 10, lineHeight: 13, fontFamily: 'Inter_600SemiBold' },
  noRecent: { fontSize: 12, fontFamily: 'Inter_400Regular', textAlign: 'center', padding: 25 },
});
