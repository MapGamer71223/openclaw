import React, { useEffect, useRef } from 'react';
import { Animated, StyleSheet, Text, View } from 'react-native';
import { router } from 'expo-router';
import { useColors } from '@/hooks/useColors';
import { LogoMark } from '@/components/ui';

export default function SplashScreen() {
  const colors = useColors();
  const opacity = useRef(new Animated.Value(0)).current;
  const scale = useRef(new Animated.Value(0.86)).current;
  useEffect(() => {
    Animated.parallel([
      Animated.timing(opacity, { toValue: 1, duration: 700, useNativeDriver: true }),
      Animated.spring(scale, { toValue: 1, friction: 8, useNativeDriver: true }),
    ]).start();
    const timer = setTimeout(() => router.replace('/(tabs)'), 1500);
    return () => clearTimeout(timer);
  }, [opacity, scale]);
  return <View style={[styles.container, { backgroundColor: colors.background }]}><Animated.View style={{ alignItems: 'center', opacity, transform: [{ scale }] }}><LogoMark /><Text style={[styles.title, { color: colors.foreground }]}>JanSatark <Text style={{ color: colors.primary }}>AI</Text></Text><Text style={[styles.tagline, { color: colors.mutedForeground }]}>Verify. Investigate. Trace.</Text><View style={[styles.scan, { backgroundColor: colors.primary }]} /></Animated.View><Text style={[styles.footer, { color: colors.mutedForeground }]}>DIGITAL MEDIA FORENSICS</Text></View>;
}

const styles = StyleSheet.create({
  container: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  title: { fontSize: 28, fontFamily: 'Inter_700Bold', marginTop: 17, letterSpacing: -0.8 },
  tagline: { fontSize: 13, fontFamily: 'Inter_400Regular', marginTop: 8, letterSpacing: 0.3 },
  scan: { height: 2, width: 112, marginTop: 34, borderRadius: 2, opacity: 0.6 },
  footer: { position: 'absolute', bottom: 46, fontSize: 9, fontFamily: 'Inter_600SemiBold', letterSpacing: 2 },
});