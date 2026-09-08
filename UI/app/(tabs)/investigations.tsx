import React, { useMemo, useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { router } from 'expo-router';
import { Feather } from '@expo/vector-icons';
import { useColors } from '@/hooks/useColors';
import { useInvestigations } from '@/context/InvestigationContext';
import { EmptyState, ErrorState, InvestigationCard, ScrollScreen, SectionHeader } from '@/components/ui';

const filters = ['All', 'AI Generated', 'AI Altered', 'Authentic', 'Inconclusive', 'Images', 'Videos'];

export default function InvestigationsScreen() {
  const colors = useColors();
  const { investigations, loading, error, refresh, setCurrent } = useInvestigations();
  const [filter, setFilter] = useState('All');
  const [search, setSearch] = useState('');
  const [refreshing, setRefreshing] = useState(false);

  const filtered = useMemo(
    () =>
      investigations.filter((item) => {
        const textMatch = item.filename.toLowerCase().includes(search.toLowerCase());
        const filterMatch =
          filter === 'All' ||
          item.verdict === filter ||
          (filter === 'Authentic' && item.verdict === 'Likely Authentic') ||
          (filter === 'Images' && item.type === 'image') ||
          (filter === 'Videos' && item.type === 'video');
        return textMatch && filterMatch;
      }),
    [filter, investigations, search],
  );

  const onRefresh = async () => {
    setRefreshing(true);
    await refresh();
    setRefreshing(false);
  };

  const openInvestigation = (id: string, item: (typeof investigations)[number]) => {
    setCurrent(item);
    if (item.status === 'processing') {
      router.push({ pathname: '/progress', params: { id } });
    } else {
      router.push({ pathname: '/results', params: { id } });
    }
  };

  return (
    <ScrollScreen refreshing={refreshing} onRefresh={onRefresh}>
      <View style={styles.titleRow}>
        <View>
          <Text style={[styles.title, { color: colors.foreground }]}>Investigations</Text>
          <Text style={[styles.subtitle, { color: colors.mutedForeground }]}>{investigations.length} evidence files analyzed</Text>
        </View>
        <Pressable onPress={() => router.push('/new-investigation')} style={[styles.add, { backgroundColor: colors.primary }]}>
          <Feather name="plus" size={19} color={colors.black} />
        </Pressable>
      </View>
      <View style={[styles.search, { backgroundColor: colors.surface, borderColor: colors.border }]}>
        <Feather name="search" size={16} color={colors.mutedForeground} />
        <TextInput value={search} onChangeText={setSearch} placeholder="Search evidence files" placeholderTextColor={colors.mutedForeground} style={[styles.input, { color: colors.foreground }]} />
      </View>
      <View style={styles.filterWrap}>
        {filters.map((item) => (
          <Pressable key={item} onPress={() => setFilter(item)} style={[styles.filter, { backgroundColor: filter === item ? `${colors.primary}20` : colors.surface, borderColor: filter === item ? colors.primary : colors.border }]}>
            <Text style={[styles.filterText, { color: filter === item ? colors.primary : colors.mutedForeground }]}>{item}</Text>
          </Pressable>
        ))}
      </View>
      <SectionHeader title="All evidence" action="Newest" />
      {error && !investigations.length ? (
        <ErrorState title="Couldn't load investigations" description={error} onRetry={refresh} />
      ) : loading && !investigations.length ? (
        <Text style={[styles.loading, { color: colors.mutedForeground }]}>Loading investigations…</Text>
      ) : filtered.length ? (
        filtered.map((item) => <InvestigationCard key={item.id} investigation={item} onPress={() => openInvestigation(item.id, item)} />)
      ) : (
        <EmptyState title="No matching investigations" description="Try another search or start a new investigation." />
      )}
      {error && investigations.length ? (
        <Text style={[styles.staleBanner, { color: colors.warning }]}>Showing cached results — {error}</Text>
      ) : null}
    </ScrollScreen>
  );
}

const styles = StyleSheet.create({
  titleRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 },
  title: { fontSize: 27, fontFamily: 'Inter_700Bold', letterSpacing: -0.8 },
  subtitle: { fontSize: 12, fontFamily: 'Inter_400Regular', marginTop: 5 },
  add: { width: 42, height: 42, borderRadius: 14, alignItems: 'center', justifyContent: 'center' },
  search: { height: 47, borderRadius: 14, borderWidth: 1, flexDirection: 'row', alignItems: 'center', paddingHorizontal: 13, gap: 9 },
  input: { flex: 1, fontSize: 12, fontFamily: 'Inter_400Regular' },
  filterWrap: { flexDirection: 'row', gap: 7, flexWrap: 'wrap', marginTop: 13 },
  filter: { paddingHorizontal: 11, paddingVertical: 7, borderRadius: 9, borderWidth: 1 },
  filterText: { fontSize: 10, fontFamily: 'Inter_600SemiBold' },
  loading: { textAlign: 'center', fontSize: 12, padding: 28 },
  staleBanner: { textAlign: 'center', fontSize: 10, fontFamily: 'Inter_500Medium', marginTop: 14 },
});
