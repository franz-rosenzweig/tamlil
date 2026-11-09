/* Tamlil's themes. A theme is a few colours in a light and a dark version, and every colour token
   app.css uses is made from them here, so text keeps its contrast in all of them. Tamlil's own is
   app.css's colours exactly. The yellow highlight (--cap) is each theme's own yellow.

   Kept per device in localStorage: tamlil.look (which theme) and tamlil.mode (auto, light or dark;
   auto follows the device). Loaded in each page's head, so the colours are on before anything shows. */
(() => {
// bg: the page; surface: the bar and cards; ink: text; accent: links and what's running;
// cap: the highlight; form: other forms of a word; good, warn, bad. Only bg, ink and accent are needed.
const TAMLIL_LIGHT = {
  '--bg': '#ECEEF1', '--surface': '#F8F9FB', '--sunk': '#E2E5EA', '--ink': '#121419', '--ink-2': '#343945', '--muted': '#5C6473',
  '--rule': '#D2D6DD', '--rule-2': '#B6BCC7', '--cap': '#FFD43B', '--cap-ink': '#17150A', '--focus': '#2851C8',
  '--form': '#07756D', '--form-bg': '#D3EEEA', '--ok': '#1F7A4A', '--ok-bg': '#D5EEDF', '--warn': '#8F5A00', '--warn-bg': '#F6E7C8',
  '--bad': '#B8322A', '--bad-bg': '#F6DAD7', '--run': '#2851C8', '--run-bg': '#DCE4F8', 'color-scheme': 'light',
};
const TAMLIL_DARK = {
  '--bg': '#0E1014', '--surface': '#161920', '--sunk': '#1E222A', '--ink': '#E7EAF0', '--ink-2': '#C2C7D0', '--muted': '#8C94A3',
  '--rule': '#2A2F39', '--rule-2': '#3D4350', '--cap': '#FFD43B', '--cap-ink': '#17150A', '--focus': '#86A5FF',
  '--form': '#62D2C5', '--form-bg': '#0F302C', '--ok': '#5BCB90', '--ok-bg': '#12301F', '--warn': '#E6B656', '--warn-bg': '#35280C',
  '--bad': '#F2796F', '--bad-bg': '#3A1714', '--run': '#86A5FF', '--run-bg': '#1A2446', 'color-scheme': 'dark',
};

const FAMILIES = [
  { id: 'tamlil', name: 'Tamlil', light: { vars: TAMLIL_LIGHT }, dark: { vars: TAMLIL_DARK } },
  { id: 'paper', name: 'Paper',
    light: { bg: '#f7f0e3', surface: '#fcf8f0', ink: '#3a3127', accent: '#9a5b1f', cap: '#f3cd5e', form: '#3f7a6e' },
    dark: { bg: '#1d1915', surface: '#241f19', ink: '#e8dcc6', accent: '#d39a5b', cap: '#e3b34f', form: '#7fbfb0' } },
  { id: 'pencil', name: 'Blue pencil',
    light: { bg: '#f4f7fa', surface: '#ffffff', ink: '#3a4450', accent: '#2e7bd6', cap: '#ffe066', form: '#1a8a7a', bad: '#d0457b' },
    dark: { bg: '#17202b', surface: '#1c2733', ink: '#cfd8e2', accent: '#5aa5f0', cap: '#e8c547', form: '#5fc9b8', bad: '#f07aa5' } },
  { id: 'nord', name: 'Nord',
    light: { bg: '#e5e9f0', surface: '#eceff4', ink: '#2e3440', accent: '#5e81ac', cap: '#ebcb8b', form: '#5e9c9b', good: '#5f8a4a', warn: '#b0703a', bad: '#bf616a' },
    dark: { bg: '#2e3440', surface: '#3b4252', ink: '#e5e9f0', accent: '#88c0d0', cap: '#ebcb8b', form: '#8fbcbb', good: '#a3be8c', warn: '#d08770', bad: '#bf616a' } },
  { id: 'solarized', name: 'Solarized',
    light: { bg: '#eee8d5', surface: '#fdf6e3', ink: '#475b62', accent: '#268bd2', cap: '#e5c35a', form: '#2aa198', good: '#859900', warn: '#cb4b16', bad: '#dc322f' },
    dark: { bg: '#002b36', surface: '#073642', ink: '#a3b1b1', accent: '#268bd2', cap: '#b58900', form: '#2aa198', good: '#859900', warn: '#cb4b16', bad: '#dc322f' } },
  { id: 'gruvbox', name: 'Gruvbox',
    light: { bg: '#f2e5bc', surface: '#fbf1c7', ink: '#3c3836', accent: '#076678', cap: '#fabd2f', form: '#427b58', good: '#79740e', warn: '#af3a03', bad: '#9d0006' },
    dark: { bg: '#282828', surface: '#32302f', ink: '#ebdbb2', accent: '#83a598', cap: '#fabd2f', form: '#8ec07c', good: '#b8bb26', warn: '#fe8019', bad: '#fb4934' } },
  { id: 'catppuccin', name: 'Catppuccin',
    light: { bg: '#e6e9ef', surface: '#eff1f5', ink: '#4c4f69', accent: '#1e66f5', cap: '#f5c56b', form: '#179299', good: '#40a02b', warn: '#fe640b', bad: '#d20f39' },
    dark: { bg: '#1e1e2e', surface: '#181825', ink: '#cdd6f4', accent: '#89b4fa', cap: '#f9e2af', form: '#94e2d5', good: '#a6e3a1', warn: '#fab387', bad: '#f38ba8' } },
  { id: 'rose-pine', name: 'Rosé Pine',
    light: { bg: '#f2e9e1', surface: '#faf4ed', ink: '#575279', accent: '#286983', cap: '#f6c177', form: '#56949f', good: '#56949f', warn: '#ea9d34', bad: '#b4637a' },
    dark: { bg: '#232136', surface: '#2a273f', ink: '#e0def4', accent: '#c4a7e7', cap: '#f6c177', form: '#9ccfd8', good: '#9ccfd8', warn: '#ea9a97', bad: '#eb6f92' } },
  { id: 'tokyo', name: 'Tokyo Night',
    light: { bg: '#d5d6db', surface: '#e1e2e7', ink: '#343b58', accent: '#2e7de9', cap: '#e0af68', form: '#387068', good: '#587539', warn: '#b15c00', bad: '#f52a65' },
    dark: { bg: '#1a1b26', surface: '#16161e', ink: '#c0caf5', accent: '#7aa2f7', cap: '#e0af68', form: '#73daca', good: '#9ece6a', warn: '#ff9e64', bad: '#f7768e' } },
  { id: 'dracula', name: 'Dracula',
    light: { bg: '#f5f0d8', surface: '#fffbeb', ink: '#1f1f1f', accent: '#644ac9', cap: '#ece05a', form: '#036a96', good: '#14710a', warn: '#a34d14', bad: '#cb3a2a' },
    dark: { bg: '#282a36', surface: '#21222c', ink: '#f8f8f2', accent: '#bd93f9', cap: '#f1fa8c', form: '#8be9fd', good: '#50fa7b', warn: '#ffb86c', bad: '#ff5555' } },
  { id: 'everforest', name: 'Everforest',
    light: { bg: '#f4f0d9', surface: '#fdf6e3', ink: '#4d5a61', accent: '#3a94c5', cap: '#e8c46a', form: '#35a77c', good: '#8da101', warn: '#f57d26', bad: '#f85552' },
    dark: { bg: '#2d353b', surface: '#343f44', ink: '#d3c6aa', accent: '#7fbbb3', cap: '#dbbc7f', form: '#83c092', good: '#a7c080', warn: '#e69875', bad: '#e67e80' } },
  { id: 'eink', name: 'E-ink',
    light: { bg: '#ebe7de', surface: '#f4f1ea', ink: '#1a1a1a', accent: '#2f2f2f', cap: '#cdc7b8', form: '#3d3d3d', good: '#2f2f2f', warn: '#2f2f2f', bad: '#1a1a1a' },
    dark: { bg: '#121212', surface: '#1a1a1a', ink: '#e8e4da', accent: '#c9c9c9', cap: '#5a5750', form: '#bdbdbd', good: '#c9c9c9', warn: '#c9c9c9', bad: '#e8e4da' } },
  { id: 'contrast', name: 'High contrast',
    light: { bg: '#ffffff', surface: '#ffffff', ink: '#000000', accent: '#0040c0', cap: '#ffe500', form: '#00695c', good: '#006b2d', warn: '#8a4b00', bad: '#b00020' },
    dark: { bg: '#000000', surface: '#0c0c0c', ink: '#ffffff', accent: '#7ab8ff', cap: '#ffe500', form: '#5ee0c8', good: '#5ee08a', warn: '#ffc061', bad: '#ff7a7a' } },
  { id: 'black', name: 'Black',
    light: { bg: '#ffffff', surface: '#ffffff', ink: '#121419', accent: '#2851C8', form: '#07756D' },
    dark: { bg: '#000000', surface: '#0c0d10', ink: '#E7EAF0', accent: '#86A5FF', form: '#62D2C5' } },
];

/* ---------- colour arithmetic ---------- */
const rgb = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16) / 255);
const hex = (c) => '#' + c.map((v) => Math.round(Math.min(1, Math.max(0, v)) * 255).toString(16).padStart(2, '0')).join('');
const mix = (a, b, t) => hex(rgb(a).map((v, i) => v + (rgb(b)[i] - v) * t));
const lum = (h) => { const [r, g, b] = rgb(h).map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4)); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
const contrast = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
// c, moved toward white or black (away from the grounds) until it reads on every one of them
const readable = (c, grounds, min) => {
  const toward = lum(grounds[0]) < 0.3 ? '#ffffff' : '#000000';
  for (let t = 0; t <= 1.001; t += 0.04) {
    const x = mix(c, toward, t);
    if (grounds.every((g) => contrast(x, g) >= min)) return x;
  }
  return toward;
};
const onFill = (f) => (contrast(f, '#ffffff') >= contrast(f, '#17150a') ? '#ffffff' : '#17150a');

// Every token app.css uses, from a palette's few colours.
function vars(p, dark) {
  if (p.vars) return p.vars;
  const base = dark ? TAMLIL_DARK : TAMLIL_LIGHT;
  const bg = p.bg, ink = p.ink;
  const surface = p.surface || (dark ? mix(bg, ink, 0.05) : mix(bg, '#ffffff', 0.6));
  const grounds = [bg, surface];
  const pair = (name, c, t) => {
    const soft = mix(bg, c, t);
    return { [`--${name}`]: readable(c, [...grounds, soft], 4.5), [`--${name}-bg`]: soft };
  };
  const cap = p.cap || '#FFD43B';
  const focus = readable(p.accent, grounds, 4.5), runBg = mix(bg, p.accent, dark ? 0.2 : 0.1);
  return {
    '--bg': bg, '--surface': surface, '--sunk': dark ? mix(bg, ink, 0.1) : mix(bg, ink, 0.06),
    '--ink': ink, '--ink-2': mix(ink, bg, 0.16), '--muted': readable(mix(ink, bg, dark ? 0.42 : 0.34), grounds, 4.5),
    '--rule': mix(bg, ink, dark ? 0.13 : 0.12), '--rule-2': mix(bg, ink, dark ? 0.22 : 0.25),
    '--cap': cap, '--cap-ink': onFill(cap), '--focus': focus,
    '--run': readable(p.accent, [...grounds, runBg], 4.5), '--run-bg': runBg,
    ...pair('form', p.form || base['--form'], dark ? 0.17 : 0.13),
    ...pair('ok', p.good || base['--ok'], dark ? 0.17 : 0.14),
    ...pair('warn', p.warn || base['--warn'], dark ? 0.17 : 0.14),
    ...pair('bad', p.bad || base['--bad'], dark ? 0.17 : 0.14),
    'color-scheme': dark ? 'dark' : 'light',
  };
}

const MODES = ['auto', 'light', 'dark'];
const media = matchMedia('(prefers-color-scheme: dark)');
const store = (k, v) => { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) {} return null; };
const byId = (id) => FAMILIES.find((f) => f.id === id) || FAMILIES[0];

function get() {
  const mode = store('tamlil.mode');
  return { look: byId(store('tamlil.look')).id, mode: MODES.includes(mode) ? mode : 'auto' };
}
const isDark = (mode) => mode === 'dark' || (mode === 'auto' && media.matches);

function apply(a) {
  a = a || get();
  const fam = byId(a.look), dark = isDark(a.mode), r = document.documentElement;
  const v = vars(dark ? fam.dark : fam.light, dark);
  for (const [k, val] of Object.entries(v)) r.style.setProperty(k, val);
  r.dataset.mode = dark ? 'dark' : 'light';
  r.dataset.look = fam.id;
  let m = document.querySelector('meta[name="theme-color"]');
  if (!m) { m = document.createElement('meta'); m.name = 'theme-color'; document.head.appendChild(m); }
  m.content = v['--surface'];
}

function set(patch) {
  const a = Object.assign(get(), patch);
  store('tamlil.look', a.look);
  store('tamlil.mode', a.mode);
  apply(a);
}

media.addEventListener('change', () => { if (get().mode === 'auto') apply(); });
window.addEventListener('storage', (e) => { if (e.key === 'tamlil.look' || e.key === 'tamlil.mode') apply(); });   // another tab
window.TamlilThemes = { FAMILIES, vars, get, set, apply, isDark, contrast };
apply();
})();
