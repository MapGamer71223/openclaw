/**
 * Semantic design tokens for the mobile app.
 *
 * These tokens mirror the naming conventions used in web artifacts (index.css)
 * so that multi-artifact projects share a cohesive visual identity.
 *
 * Replace the placeholder values below with values that match the project's
 * brand. If a sibling web artifact exists, read its index.css and convert the
 * HSL values to hex so both artifacts use the same palette.
 *
 * To add dark mode, add a `dark` key with the same token names.
 * The useColors() hook will automatically pick it up.
 */

const colors = {
  light: {
    text: '#111A24',
    tint: '#008EAE',
    background: '#F5F8FA',
    foreground: '#111A24',
    card: '#FFFFFF',
    cardForeground: '#111A24',
    primary: '#008EAE',
    primaryForeground: '#FFFFFF',
    secondary: '#EDF2F5',
    secondaryForeground: '#23303B',
    muted: '#DCE5EB',
    mutedForeground: '#5D6C78',
    accent: '#6E4DE6',
    accentForeground: '#FFFFFF',
    destructive: '#D93434',
    destructiveForeground: '#FFFFFF',
    border: '#D7E0E7',
    input: '#E5EDF2',
    success: '#189A4D',
    warning: '#B97800',
    orange: '#C75A0A',
    surface: '#EEF3F6',
    white: '#FFFFFF',
    black: '#111A24',
  },
  dark: {
    text: '#F3F7FA',
    tint: '#00D4FF',
    background: '#0B0F14',
    foreground: '#F3F7FA',
    card: '#18212B',
    cardForeground: '#F3F7FA',
    primary: '#00D4FF',
    primaryForeground: '#071017',
    secondary: '#151C25',
    secondaryForeground: '#C5D0D9',
    muted: '#202B37',
    mutedForeground: '#8C9AA8',
    accent: '#7C5CFC',
    accentForeground: '#FFFFFF',
    destructive: '#EF4444',
    destructiveForeground: '#FFFFFF',
    border: '#273440',
    input: '#202B37',
    success: '#22C55E',
    warning: '#F59E0B',
    orange: '#F97316',
    surface: '#151C25',
    white: '#FFFFFF',
    black: '#071017',
  },
  radius: 20,
};

export default colors;
