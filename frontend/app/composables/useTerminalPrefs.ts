import type { ITheme } from '@xterm/xterm';
import { ref, watch } from 'vue';

/**
 * 임베드 터미널 외관 설정 (폰트/테마). 브라우저 localStorage 에 영속화.
 * 멀티-Mac 동기화가 필요해지면 t_aidesk_setting 로 옮길 수 있도록 인터페이스만 추상화한다.
 */

const STORAGE_KEY = 'aidesk.terminal.prefs.v1';

export interface TerminalPrefs {
  fontSize: number;
  fontFamily: string;
  themeName: string;
}

interface TerminalThemePreset {
  name: string;
  label: string;
  theme: ITheme;
}

/** 화면에 노출되는 폰트 후보 — 시스템에 없으면 fallback 으로 자연 처리. */
export const FONT_FAMILY_PRESETS: { value: string; label: string }[] = [
  { value: 'JetBrains Mono, Menlo, Monaco, "D2Coding", monospace', label: 'JetBrains Mono' },
  { value: 'Menlo, Monaco, "D2Coding", monospace', label: 'Menlo (macOS 기본)' },
  { value: '"Fira Code", Menlo, monospace', label: 'Fira Code' },
  { value: '"SF Mono", Menlo, monospace', label: 'SF Mono' },
  { value: '"Cascadia Code", Menlo, monospace', label: 'Cascadia Code' },
];

export const THEME_PRESETS: TerminalThemePreset[] = [
  {
    name: 'aidesk-dark',
    label: 'AI Desk Dark',
    theme: {
      background: '#1E293B', foreground: '#E2E8F0', cursor: '#0062ff',
      cursorAccent: '#1E293B', selectionBackground: 'rgba(0, 98, 255, 0.30)',
      black: '#1E293B', red: '#FF6B6B', green: '#51CF66', yellow: '#FFD43B',
      blue: '#74C0FC', magenta: '#E599F7', cyan: '#3BC9DB', white: '#F1F3F5',
      brightBlack: '#475569', brightRed: '#FF8787', brightGreen: '#69DB7C',
      brightYellow: '#FFE066', brightBlue: '#91A7FF', brightMagenta: '#F783AC',
      brightCyan: '#66D9E8', brightWhite: '#FFFFFF',
    },
  },
  {
    name: 'one-dark',
    label: 'One Dark',
    theme: {
      background: '#282C34', foreground: '#ABB2BF', cursor: '#528BFF',
      cursorAccent: '#282C34', selectionBackground: 'rgba(82, 139, 255, 0.30)',
      black: '#282C34', red: '#E06C75', green: '#98C379', yellow: '#E5C07B',
      blue: '#61AFEF', magenta: '#C678DD', cyan: '#56B6C2', white: '#ABB2BF',
      brightBlack: '#5C6370', brightRed: '#E06C75', brightGreen: '#98C379',
      brightYellow: '#E5C07B', brightBlue: '#61AFEF', brightMagenta: '#C678DD',
      brightCyan: '#56B6C2', brightWhite: '#FFFFFF',
    },
  },
  {
    name: 'dracula',
    label: 'Dracula',
    theme: {
      background: '#282A36', foreground: '#F8F8F2', cursor: '#BD93F9',
      cursorAccent: '#282A36', selectionBackground: 'rgba(189, 147, 249, 0.30)',
      black: '#21222C', red: '#FF5555', green: '#50FA7B', yellow: '#F1FA8C',
      blue: '#BD93F9', magenta: '#FF79C6', cyan: '#8BE9FD', white: '#F8F8F2',
      brightBlack: '#6272A4', brightRed: '#FF6E6E', brightGreen: '#69FF94',
      brightYellow: '#FFFFA5', brightBlue: '#D6ACFF', brightMagenta: '#FF92DF',
      brightCyan: '#A4FFFF', brightWhite: '#FFFFFF',
    },
  },
  {
    name: 'solarized-light',
    label: 'Solarized Light',
    theme: {
      background: '#FDF6E3', foreground: '#657B83', cursor: '#586E75',
      cursorAccent: '#FDF6E3', selectionBackground: 'rgba(101, 123, 131, 0.20)',
      black: '#073642', red: '#DC322F', green: '#859900', yellow: '#B58900',
      blue: '#268BD2', magenta: '#D33682', cyan: '#2AA198', white: '#EEE8D5',
      brightBlack: '#002B36', brightRed: '#CB4B16', brightGreen: '#586E75',
      brightYellow: '#657B83', brightBlue: '#839496', brightMagenta: '#6C71C4',
      brightCyan: '#93A1A1', brightWhite: '#FDF6E3',
    },
  },
];

const defaults: TerminalPrefs = {
  fontSize: 14,
  fontFamily: FONT_FAMILY_PRESETS[0]!.value,
  themeName: 'aidesk-dark',
};

function load(): TerminalPrefs {
  if (typeof window === 'undefined') return { ...defaults };
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...defaults };
    const parsed = JSON.parse(raw) as Partial<TerminalPrefs>;
    return { ...defaults, ...parsed };
  } catch {
    return { ...defaults };
  }
}

function save(v: TerminalPrefs): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(v));
  } catch { /* 쿼터 초과 등 — 다음 변경시 자동 재시도 */ }
}

// 전역 단일 인스턴스 — 사이드 패널 안팎 어디서 useTerminalPrefs() 를 부르든 같은 ref 공유.
const state = ref<TerminalPrefs>(load());
watch(state, (v) => save(v), { deep: true });

export function useTerminalPrefs() {
  function themeFor(name: string): ITheme {
    return (THEME_PRESETS.find((p) => p.name === name) ?? THEME_PRESETS[0]!).theme;
  }
  return { prefs: state, themes: THEME_PRESETS, fontFamilies: FONT_FAMILY_PRESETS, themeFor };
}
