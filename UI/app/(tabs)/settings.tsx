import React, { useState } from 'react';
import { Alert, Pressable, StyleSheet, Switch, Text, View } from 'react-native';
import { Feather, MaterialCommunityIcons } from '@expo/vector-icons';
import { useColors } from '@/hooks/useColors';
import { useTheme } from '@/context/ThemeContext';
import { useInvestigations } from '@/context/InvestigationContext';
import { ScrollScreen } from '@/components/ui';

function SettingRow({ icon, title, detail, children, onPress }: { icon: keyof typeof MaterialCommunityIcons.glyphMap; title: string; detail?: string; children?: React.ReactNode; onPress?: () => void }) {
  const colors = useColors();
  return <Pressable onPress={onPress} style={styles.row}><View style={[styles.rowIcon, { backgroundColor: colors.surface }]}><MaterialCommunityIcons name={icon} size={18} color={colors.primary} /></View><View style={styles.rowCopy}><Text style={[styles.rowTitle, { color: colors.foreground }]}>{title}</Text>{detail ? <Text style={[styles.rowDetail, { color: colors.mutedForeground }]}>{detail}</Text> : null}</View>{children ?? <Feather name="chevron-right" size={17} color={colors.mutedForeground} />}</Pressable>;
}

export default function SettingsScreen() {
  const colors = useColors();
  const { clearHistory } = useInvestigations();
  const { mode, setMode } = useTheme();
  const [notifications, setNotifications] = useState(true);
  const handleClear = () => Alert.alert('Clear local history?', 'This clears the investigation list cached on this device. Your investigations remain stored on the JanSatark AI server and will reappear next time you refresh.', [{ text: 'Cancel', style: 'cancel' }, { text: 'Clear history', style: 'destructive', onPress: clearHistory }]);
  const showPrivacy = () => Alert.alert('Privacy', 'JanSatark AI uploads media to the JanSatark AI backend for analysis and stores investigation results there. A copy of the investigation list is cached on this device for fast loading and offline viewing.', [{ text: 'Done' }]);
  const showTerms = () => Alert.alert('Terms of use', 'This preview provides informational media analysis only. Always verify important evidence with qualified forensic professionals before making decisions.', [{ text: 'Done' }]);
  return <ScrollScreen><Text style={[styles.title, { color: colors.foreground }]}>Settings</Text><Text style={[styles.subtitle, { color: colors.mutedForeground }]}>Tune your investigation workspace</Text><View style={[styles.section, { backgroundColor: colors.card, borderColor: colors.border }]}><SettingRow icon="weather-night" title="Dark mode" detail={mode === 'dark' ? 'Always use the dark appearance' : 'Use a brighter appearance'}><Switch value={mode === 'dark'} onValueChange={(enabled) => setMode(enabled ? 'dark' : 'light')} trackColor={{ false: colors.muted, true: `${colors.primary}70` }} thumbColor={mode === 'dark' ? colors.primary : colors.mutedForeground} /></SettingRow><View style={[styles.divider, { backgroundColor: colors.border }]} /><SettingRow icon="bell-outline" title="Investigation notifications" detail="Get notified when a scan is ready"><Switch value={notifications} onValueChange={setNotifications} trackColor={{ false: colors.muted, true: `${colors.primary}70` }} thumbColor={notifications ? colors.primary : colors.mutedForeground} /></SettingRow></View><Text style={[styles.groupTitle, { color: colors.mutedForeground }]}>DATA & PRIVACY</Text><View style={[styles.section, { backgroundColor: colors.card, borderColor: colors.border }]}><SettingRow icon="delete-outline" title="Clear local history" detail="Remove all saved investigations" onPress={handleClear} /><View style={[styles.divider, { backgroundColor: colors.border }]} /><SettingRow icon="shield-lock-outline" title="Privacy" detail="How local evidence is handled" onPress={showPrivacy} /><View style={[styles.divider, { backgroundColor: colors.border }]} /><SettingRow icon="file-document-outline" title="Terms of use" detail="Important information about analysis" onPress={showTerms} /></View><View style={styles.brand}><MaterialCommunityIcons name="shield-check-outline" size={19} color={colors.primary} /><Text style={[styles.brandText, { color: colors.foreground }]}>JanSatark AI</Text><Text style={[styles.version, { color: colors.mutedForeground }]}>Version 1.0.0</Text></View></ScrollScreen>;
}

const styles = StyleSheet.create({
  title: { fontSize: 27, fontFamily: 'Inter_700Bold', letterSpacing: -0.8 },
  subtitle: { fontSize: 12, fontFamily: 'Inter_400Regular', marginTop: 5, marginBottom: 25 },
  section: { borderWidth: 1, borderRadius: 19, paddingHorizontal: 15 },
  row: { minHeight: 70, flexDirection: 'row', alignItems: 'center', gap: 12 },
  rowIcon: { width: 36, height: 36, borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
  rowCopy: { flex: 1 },
  rowTitle: { fontSize: 12, fontFamily: 'Inter_600SemiBold' },
  rowDetail: { fontSize: 10, fontFamily: 'Inter_400Regular', marginTop: 4 },
  divider: { height: 1, marginLeft: 48 },
  groupTitle: { fontSize: 10, fontFamily: 'Inter_700Bold', letterSpacing: 1.4, marginTop: 28, marginBottom: 10 },
  brand: { alignItems: 'center', marginTop: 48, gap: 6 },
  brandText: { fontSize: 13, fontFamily: 'Inter_700Bold' },
  version: { fontSize: 10, fontFamily: 'Inter_400Regular' },
});