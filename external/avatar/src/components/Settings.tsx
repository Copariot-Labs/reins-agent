import { useState, useEffect } from 'react';
import type { JSX } from 'react';
import { ModelSettings } from './ModelSettings';
import { MemoryStatePanel } from './MemoryStatePanel';
import {
  getConfig,
  saveConfig,
  resetAllAppData,
  resetOnboarding,
  getVoices,
} from '../api/tauri';
import { ACP_AGENT_PRESET_IDS, ACP_AGENT_PRESETS } from '../lib/agentPresets';
import {
  DEFAULT_TTS_PROVIDER,
  DEFAULT_TTS_VOICE,
  TTS_PRESETS_UI,
} from '../lib/ttsPresets';
import { previewSystemChineseVoice } from '../audio/systemSpeech';
import { AgentPresetCard } from './agents/AgentPresetCard';
import { AgentPresetIcon } from './agents/AgentPresetIcon';
import { AgentSetupPanel } from './agents/AgentSetupPanel';
import { MeuxeMark } from './ui/MeuxeMark';
import { AvatarViewportSettings } from './settings/AvatarViewportSettings';
import type { AcpAgentPresetId } from '../lib/agentPresets';
import { useLanguage } from '../i18n/LanguageContext';
interface Voice {
  id: string;
  name: string;
}

type SettingsPage =
  | null
  | 'profile'
  | 'llm'
  | 'tts'
  | 'privacy'
  | 'expressions'
  | 'memory'
  | 'avatar';

const SETTINGS_TTS_PRESETS: Record<
  string,
  { name: string; needs_key: boolean }
> = {
  system: TTS_PRESETS_UI.system,
  tiktok: TTS_PRESETS_UI.tiktok,
  elevenlabs: TTS_PRESETS_UI.elevenlabs,
};

const ProfileIcon = () => (
  <svg
    className='w-5 h-5'
    fill='none'
    stroke='currentColor'
    viewBox='0 0 24 24'
  >
    <path
      strokeLinecap='round'
      strokeLinejoin='round'
      strokeWidth={1.8}
      d='M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z'
    />
  </svg>
);
const SpeakerIcon = () => (
  <svg
    className='w-5 h-5'
    fill='none'
    stroke='currentColor'
    viewBox='0 0 24 24'
  >
    <path
      strokeLinecap='round'
      strokeLinejoin='round'
      strokeWidth={1.8}
      d='M15.536 8.464a5 5 0 010 7.072m2.828-9.9a9 9 0 010 12.728M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z'
    />
  </svg>
);
const MaskIcon = () => (
  <svg
    className='w-5 h-5'
    fill='none'
    stroke='currentColor'
    viewBox='0 0 24 24'
  >
    <path
      strokeLinecap='round'
      strokeLinejoin='round'
      strokeWidth={1.8}
      d='M14.828 14.828a4 4 0 01-5.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z'
    />
  </svg>
);
const ShieldIcon = () => (
  <svg
    className='w-5 h-5'
    fill='none'
    stroke='currentColor'
    viewBox='0 0 24 24'
  >
    <path
      strokeLinecap='round'
      strokeLinejoin='round'
      strokeWidth={1.8}
      d='M12 3l7 4v5c0 4.5-2.8 7.7-7 9-4.2-1.3-7-4.5-7-9V7l7-4z'
    />
    <path
      strokeLinecap='round'
      strokeLinejoin='round'
      strokeWidth={1.8}
      d='M9 12l2 2 4-4'
    />
  </svg>
);
const ArchiveIcon = () => (
  <svg
    className='w-5 h-5'
    fill='none'
    stroke='currentColor'
    viewBox='0 0 24 24'
  >
    <path
      strokeLinecap='round'
      strokeLinejoin='round'
      strokeWidth={1.8}
      d='M5 8h14M5 12h10M5 16h8M4 4h16v16H4z'
    />
  </svg>
);
const FrameIcon = () => (
  <svg
    className='w-5 h-5'
    fill='none'
    stroke='currentColor'
    viewBox='0 0 24 24'
  >
    <path
      strokeLinecap='round'
      strokeLinejoin='round'
      strokeWidth={1.8}
      d='M4 5a1 1 0 011-1h14a1 1 0 011 1v14a1 1 0 01-1 1H5a1 1 0 01-1-1V5z'
    />
    <path
      strokeLinecap='round'
      strokeLinejoin='round'
      strokeWidth={1.8}
      d='M9 3v18M15 3v18'
    />
  </svg>
);
type MenuItemId = 'profile' | 'privacy' | 'memory' | 'avatar' | 'expressions';

const MENU_ITEMS: {
  id: MenuItemId;
  label: string;
  description: string;
  icon: () => JSX.Element;
}[] = [
  {
    id: 'profile',
    label: 'Your Profile',
    description: 'Name and about yourself',
    icon: ProfileIcon,
  },
  {
    id: 'privacy',
    label: 'Privacy',
    description: 'What stays on your device',
    icon: ShieldIcon,
  },
  {
    id: 'memory',
    label: 'Memory',
    description: 'What your companion remembers',
    icon: ArchiveIcon,
  },
  {
    id: 'avatar',
    label: 'Avatar on screen',
    description: 'Zoom and background',
    icon: FrameIcon,
  },
  {
    id: 'expressions',
    label: 'Expressions',
    description: 'Emotions on their avatar',
    icon: MaskIcon,
  },
];

const inputClass =
  'w-full px-5 py-3.5 rounded-2xl bg-slate-50 hover:bg-slate-100/50 text-slate-700 text-[15px] outline-none transition-all placeholder-slate-400 border border-slate-100 focus:bg-white focus:ring-2 focus:ring-blue-100 focus:border-blue-300 mb-5';
const labelClass =
  'block text-sm font-semibold text-slate-700 tracking-wide mb-2 pl-1';
const buttonClass =
  'w-full py-3.5 rounded-2xl bg-blue-500 text-white text-[15px] font-semibold hover:bg-blue-600 shadow-md shadow-blue-500/20 disabled:opacity-50 hover:-translate-y-0.5 transition-all active:translate-y-0';

function LocalFirstNotice({
  variant = 'blue',
}: {
  variant?: 'blue' | 'emerald' | 'amber';
}) {
  const { tr } = useLanguage();
  const colors = {
    blue: 'border-blue-100 bg-blue-50 text-blue-800',
    emerald: 'border-emerald-100 bg-emerald-50 text-emerald-800',
    amber: 'border-amber-100 bg-amber-50 text-amber-800',
  };
  return (
    <div
      className={`mb-5 rounded-2xl border px-4 py-3 text-sm leading-snug ${colors[variant]}`}
    >
      {tr(
        'Memory and chat stay on this device. Voice and your CLI agent only use the network when you configure them.',
        '记忆和聊天记录保留在本设备上。仅当你配置语音或 CLI 智能体时才会使用网络。',
      )}
    </div>
  );
}

function PrivacyCard({
  title,
  items,
  tone,
}: {
  title: string;
  items: string[];
  tone: 'emerald' | 'blue' | 'amber';
}) {
  const toneClass = {
    emerald: 'border-emerald-100 bg-emerald-50 text-emerald-700',
    blue: 'border-blue-100 bg-blue-50 text-blue-700',
    amber: 'border-amber-100 bg-amber-50 text-amber-700',
  }[tone];
  return (
    <section className={`rounded-[1.75rem] border px-5 py-5 ${toneClass}`}>
      <h3 className='text-lg font-bold'>{title}</h3>
      <ul className='mt-3 space-y-2 text-sm leading-relaxed'>
        {items.map((item) => (
          <li key={item} className='flex gap-2'>
            <span className='mt-2 h-1.5 w-1.5 rounded-full bg-current opacity-70' />
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function Settings({
  onClose,
  characterId,
  characterName,
  modelId,
  onPreviewExpression,
  onExpressionsSaved,
  onConversationCleared,
  onResetAll,
  onResetOnboarding,
  avatarZoom,
  avatarBackground,
  onAvatarZoomChange,
  onAvatarBackgroundChange,
}: {
  onClose: () => void;
  characterId?: string;
  characterName: string;
  modelId?: string;
  onPreviewExpression?: (expr: string) => void;
  onExpressionsSaved?: () => void;
  onConversationCleared?: () => void;
  onResetAll?: () => void;
  onResetOnboarding?: () => void;
  avatarZoom?: number;
  avatarBackground?: string;
  onAvatarZoomChange?: (zoom: number) => void;
  onAvatarBackgroundChange?: (bg: string) => void;
}) {
  const { language, setLanguage, tr } = useLanguage();
  const [page, setPage] = useState<SettingsPage>(null);
  const [config, setConfig] = useState<any>(null);
  const [voices, setVoices] = useState<Voice[]>([]);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const isMac = navigator.platform.toUpperCase().includes('MAC');

  const [configuredTts, setConfiguredTts] = useState<
    Record<string, { configured: boolean; voice: string }>
  >({});

  const [userName, setUserName] = useState('');
  const [userAbout, setUserAbout] = useState('');
  const [ttsProvider, setTtsProvider] = useState(DEFAULT_TTS_PROVIDER);
  const [ttsApiKey, setTtsApiKey] = useState('');
  const [ttsVoice, setTtsVoice] = useState(DEFAULT_TTS_VOICE);
  const [voicePreviewing, setVoicePreviewing] = useState(false);
  const [voicePreviewError, setVoicePreviewError] = useState('');
  const [agentPreset, setAgentPreset] = useState('reins');
  const [agentProgram, setAgentProgram] = useState('');
  const [agentArgs, setAgentArgs] = useState('');
  const [confirmReset, setConfirmReset] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [resetError, setResetError] = useState<string | null>(null);
  const [resettingOnboarding, setResettingOnboarding] = useState(false);
  const [onboardingResetError, setOnboardingResetError] = useState<
    string | null
  >(null);

  const deriveConfigured = (cfg: any) => {
    const ttsConfigured: Record<
      string,
      { configured: boolean; voice: string }
    > = {};

    if (cfg?.tts_providers) {
      for (const [id, prov] of Object.entries(
        cfg.tts_providers as Record<string, any>,
      )) {
        ttsConfigured[id] = {
          configured: true,
          voice: (prov as any).voice || '',
        };
      }
    }
    if (cfg?.tts?.provider) {
      ttsConfigured[cfg.tts.provider] = {
        configured: true,
        voice: cfg.tts.voice || '',
      };
    }

    setConfiguredTts(ttsConfigured);
  };

  useEffect(() => {
    getConfig()
      .then((cfg: any) => {
        setConfig(cfg);
        deriveConfigured(cfg);

        setUserName(cfg.user?.name || '');
        setUserAbout(cfg.user?.about || '');
        setTtsProvider(cfg.tts?.provider || DEFAULT_TTS_PROVIDER);
        setTtsApiKey('');
        setTtsVoice(cfg.tts?.voice || DEFAULT_TTS_VOICE);
        setAgentPreset(cfg.agent?.preset || 'reins');
        setAgentProgram(cfg.agent?.program || '');
        setAgentArgs((cfg.agent?.args || []).join(' '));
      })
      .catch((err) => console.error('Failed to load config:', err));
  }, []);

  useEffect(() => {
    getVoices(ttsProvider)
      .then((availableVoices) => {
        setVoices(availableVoices);
        setTtsVoice((currentVoice) =>
          availableVoices.some((voice) => voice.id === currentVoice)
            ? currentVoice
            : availableVoices[0]?.id || DEFAULT_TTS_VOICE,
        );
      })
      .catch(console.error);
  }, [ttsProvider]);

  const handleSave = async () => {
    setSaving(true);
    const update: any = {
      user: { name: userName, about: userAbout },
      tts: { provider: ttsProvider, voice: ttsVoice },
      agent: {
        preset: agentPreset,
        program: agentProgram,
        args: agentArgs.trim() ? agentArgs.trim().split(/\s+/) : [],
      },
    };
    if (ttsApiKey) update.tts.api_key = ttsApiKey;
    try {
      await saveConfig(update);

      // Refresh config to update configured status
      const freshConfig: any = await getConfig();
      setConfig(freshConfig);
      deriveConfigured(freshConfig);
    } catch (err) {
      console.error('Failed to save config:', err);
    }

    setSaving(false);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const handleSystemVoicePreview = async () => {
    setVoicePreviewError('');
    setVoicePreviewing(true);
    try {
      await previewSystemChineseVoice(ttsVoice);
    } catch (error) {
      setVoicePreviewError(
        error instanceof Error ? error.message : String(error),
      );
    } finally {
      setVoicePreviewing(false);
    }
  };

  if (!config)
    return (
      <div className='p-8 text-slate-400'>
        {tr('Loading settings...', '正在加载设置...')}
      </div>
    );

  // ========== SUB-PAGE HEADER ==========
  const SubHeader = ({ title }: { title: string }) => (
    <div className='flex items-center gap-4 mb-8'>
      <button
        onClick={() => setPage(null)}
        className='w-10 h-10 rounded-full bg-white border border-slate-100 shadow-sm shadow-blue-900/5 hover:shadow-md hover:-translate-y-0.5 flex items-center justify-center text-slate-500 hover:text-blue-500 transition-all'
      >
        <svg width='18' height='18' viewBox='0 0 16 16' fill='none'>
          <path
            d='M10 12L6 8L10 4'
            stroke='currentColor'
            strokeWidth='2.5'
            strokeLinecap='round'
            strokeLinejoin='round'
          />
        </svg>
      </button>
      <h2 className='text-xl font-bold text-slate-800 tracking-tight'>
        {title}
      </h2>
    </div>
  );

  // ========== MENU LIST ==========
  if (page === null) {
    return (
      <div className='flex-1 overflow-y-auto p-6 scrollbar-thin scrollbar-thumb-slate-200 scrollbar-track-transparent'>
        <div className='flex items-center justify-between mb-6'>
          <div className='flex items-center gap-3'>
            <MeuxeMark className='h-11 w-11 shrink-0' />
            <div>
              <h2 className='text-xl font-bold text-slate-800 tracking-tight'>
                {tr('Settings', '设置')}
              </h2>
              <p className='text-sm text-slate-400'>
                {tr(
                  'Local companion · optional cloud voice & agents',
                  '本地伙伴 · 可选云端语音与智能体',
                )}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className='w-10 h-10 rounded-full bg-white border border-slate-100 shadow-sm shadow-blue-900/5 hover:shadow-md hover:-translate-y-0.5 flex items-center justify-center text-slate-500 hover:text-red-500 transition-all'
          >
            <svg width='14' height='14' viewBox='0 0 16 16' fill='none'>
              <path
                d='M3 3L13 13M13 3L3 13'
                stroke='currentColor'
                strokeWidth='2.5'
                strokeLinecap='round'
                strokeLinejoin='round'
              />
            </svg>
          </button>
        </div>

        <div className='mb-5 flex items-center justify-between gap-4 border-y border-slate-100 py-4'>
          <div>
            <div className='text-sm font-semibold text-slate-700'>
              {tr('Interface language', '界面语言')}
            </div>
            <div className='mt-0.5 text-xs text-slate-400'>
              {tr('Applied across the avatar app', '应用于整个虚拟伙伴界面')}
            </div>
          </div>
          <div
            className='flex shrink-0 rounded-xl border border-slate-200 bg-slate-50 p-1'
            role='group'
            aria-label={tr('Interface language', '界面语言')}
          >
            <button
              type='button'
              aria-pressed={language === 'zh-CN'}
              onClick={() => setLanguage('zh-CN')}
              className={`min-w-16 rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors ${
                language === 'zh-CN'
                  ? 'bg-white text-blue-700 shadow-sm'
                  : 'text-slate-500 hover:text-slate-800'
              }`}
            >
              中文
            </button>
            <button
              type='button'
              aria-pressed={language === 'en'}
              onClick={() => setLanguage('en')}
              className={`min-w-16 rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors ${
                language === 'en'
                  ? 'bg-white text-blue-700 shadow-sm'
                  : 'text-slate-500 hover:text-slate-800'
              }`}
            >
              English
            </button>
          </div>
        </div>

        <div className='mb-5 grid grid-cols-2 gap-3'>
          <button
            type='button'
            onClick={() => setPage('llm')}
            className='rounded-2xl border border-slate-100 bg-white p-3.5 shadow-sm text-left transition-all hover:border-indigo-100 hover:shadow-md group'
          >
            <div className='flex items-center gap-3'>
              <AgentPresetIcon
                id={(config.agent?.preset as AcpAgentPresetId) || 'reins'}
                size='sm'
              />
              <div className='min-w-0 flex-1'>
                <div className='text-[10px] font-semibold uppercase tracking-wide text-slate-400'>
                  {tr('Agent', '智能体')}
                </div>
                <div className='text-sm font-bold text-slate-800 truncate group-hover:text-blue-600'>
                  {ACP_AGENT_PRESETS[
                    (config.agent?.preset as AcpAgentPresetId) || 'opencode'
                  ]?.title || '—'}
                </div>
              </div>
              <svg
                className='w-4 h-4 shrink-0 text-slate-300 group-hover:text-blue-400'
                fill='none'
                viewBox='0 0 16 16'
              >
                <path
                  d='M6 4L10 8L6 12'
                  stroke='currentColor'
                  strokeWidth='2'
                  strokeLinecap='round'
                  strokeLinejoin='round'
                />
              </svg>
            </div>
          </button>
          <button
            type='button'
            onClick={() => setPage('tts')}
            className='rounded-2xl border border-slate-100 bg-white p-3.5 shadow-sm text-left transition-all hover:border-indigo-100 hover:shadow-md group'
          >
            <div className='flex items-center gap-3'>
              <div className='flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-blue-600 text-white shadow-sm'>
                <SpeakerIcon />
              </div>
              <div className='min-w-0 flex-1'>
                <div className='text-[10px] font-semibold uppercase tracking-wide text-slate-400'>
                  {tr('Voice', '语音')}
                </div>
                <div className='text-sm font-bold text-slate-800 truncate group-hover:text-blue-600'>
                  {tr(
                    TTS_PRESETS_UI[config.tts?.provider]?.name ||
                      config.tts?.provider ||
                      '—',
                    {
                      system: '系统中文',
                      tiktok: 'Reins 语音',
                      elevenlabs: 'ElevenLabs',
                      openai_tts: 'OpenAI 语音',
                    }[config.tts?.provider as string] ||
                      config.tts?.provider ||
                      '—',
                  )}
                </div>
              </div>
              <svg
                className='w-4 h-4 shrink-0 text-slate-300 group-hover:text-blue-400'
                fill='none'
                viewBox='0 0 16 16'
              >
                <path
                  d='M6 4L10 8L6 12'
                  stroke='currentColor'
                  strokeWidth='2'
                  strokeLinecap='round'
                  strokeLinejoin='round'
                />
              </svg>
            </div>
          </button>
        </div>

        <div className='space-y-3'>
          {MENU_ITEMS.map((item) => (
            <button
              key={item.id}
              onClick={() => setPage(item.id)}
              className='w-full flex items-center gap-4 px-4 py-3.5 rounded-2xl border border-slate-100/80 bg-white shadow-sm shadow-slate-900/5 hover:border-indigo-100 hover:shadow-md transition-all text-left group'
            >
              <div className='w-11 h-11 rounded-2xl bg-slate-50 group-hover:bg-indigo-50 flex items-center justify-center text-slate-500 group-hover:text-indigo-600 transition-colors shadow-sm shrink-0'>
                <item.icon />
              </div>
              <div className='flex-1 min-w-0'>
                <div className='text-[15px] font-semibold text-slate-700 group-hover:text-blue-600 transition-colors'>
                  {tr(
                    item.label,
                    {
                      profile: '个人资料',
                      privacy: '隐私',
                      memory: '记忆',
                      avatar: '屏幕形象',
                      expressions: '表情',
                    }[item.id] || item.label,
                  )}
                </div>
                <div className='text-sm text-slate-400 mt-1'>
                  {tr(
                    item.description,
                    {
                      profile: '姓名与个人介绍',
                      privacy: '了解哪些内容保留在设备上',
                      memory: '管理伙伴记住的内容',
                      avatar: '缩放与背景',
                      expressions: '设置虚拟形象的情绪',
                    }[item.id] || item.description,
                  )}
                </div>
              </div>
              <svg
                className='w-5 h-5 text-slate-300 group-hover:text-blue-400 transition-colors'
                fill='none'
                viewBox='0 0 16 16'
              >
                <path
                  d='M6 4L10 8L6 12'
                  stroke='currentColor'
                  strokeWidth='2'
                  strokeLinecap='round'
                  strokeLinejoin='round'
                />
              </svg>
            </button>
          ))}
        </div>
      </div>
    );
  }

  // ========== PROFILE PAGE ==========
  if (page === 'profile') {
    return (
      <div className='flex-1 overflow-y-auto p-6 scrollbar-thin scrollbar-thumb-slate-200 scrollbar-track-transparent'>
        <SubHeader title={tr('Your Profile', '个人资料')} />

        <label className={labelClass}>{tr('Your Name', '你的名字')}</label>
        <input
          type='text'
          value={userName}
          onChange={(e) => setUserName(e.target.value)}
          placeholder={tr(
            'What should your companion call you?',
            '希望伙伴如何称呼你？',
          )}
          className={inputClass}
        />

        <label className={labelClass}>{tr('About Yourself', '关于你')}</label>
        <textarea
          value={userAbout}
          onChange={(e) => setUserAbout(e.target.value)}
          placeholder={tr(
            'Tell your companion about yourself -- interests, what you do, what you enjoy...',
            '告诉伙伴你的兴趣、工作和喜欢的事情...',
          )}
          rows={5}
          className={`${inputClass} resize-none mb-8 rounded-3xl`}
        />

        <button onClick={handleSave} disabled={saving} className={buttonClass}>
          {saving
            ? tr('Saving...', '正在保存...')
            : saved
              ? tr('Saved!', '已保存！')
              : tr('Save Profile', '保存资料')}
        </button>

        {/* Keyboard Shortcuts */}
        <div className='mt-10'>
          <h3 className='text-sm font-bold text-slate-700 uppercase tracking-wider mb-4 pl-1'>
            {tr('Keyboard Shortcuts', '键盘快捷键')}
          </h3>
          <div className='rounded-2xl border border-slate-100 bg-white overflow-hidden'>
            {[
              {
                keys: isMac ? 'Cmd + Shift + E' : 'Ctrl + Shift + E',
                action: tr('Toggle mini mode', '切换迷你模式'),
                context: tr(
                  'Global — works from any app',
                  '全局 — 可在任何应用中使用',
                ),
              },
              {
                keys: isMac ? 'Cmd + Shift + Space' : 'Ctrl + Shift + Space',
                action: tr('Open text input', '打开文字输入'),
                context: tr('Global — mini mode', '全局 — 迷你模式'),
              },
              {
                keys: isMac ? 'Cmd + Shift + M' : 'Ctrl + Shift + M',
                action: tr('Toggle microphone', '切换麦克风'),
                context: tr('Global — mini mode', '全局 — 迷你模式'),
              },
              {
                keys: 'Escape',
                action: tr('Close text input', '关闭文字输入'),
                context: tr('Mini mode', '迷你模式'),
              },
            ].map((shortcut, i) => (
              <div
                key={i}
                className={`flex items-center justify-between px-4 py-3 ${i > 0 ? 'border-t border-slate-50' : ''}`}
              >
                <div className='flex-1'>
                  <span className='text-[13px] text-slate-700'>
                    {shortcut.action}
                  </span>
                  <span className='text-[11px] text-slate-400 ml-2'>
                    {shortcut.context}
                  </span>
                </div>
                <div className='flex gap-1'>
                  {shortcut.keys.split(' + ').map((key, j) => (
                    <span key={j}>
                      {j > 0 && (
                        <span className='text-slate-300 text-[11px] mx-0.5'>
                          +
                        </span>
                      )}
                      <kbd className='inline-block px-2 py-0.5 text-[11px] font-semibold text-slate-600 bg-slate-50 border border-slate-200 rounded-lg shadow-sm'>
                        {key}
                      </kbd>
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  // ========== LLM PAGE ==========
  if (page === 'llm') {
    const presetId = (agentPreset as AcpAgentPresetId) || 'reins';
    return (
      <div className='flex-1 overflow-y-auto p-6 scrollbar-thin scrollbar-thumb-slate-200 scrollbar-track-transparent'>
        <SubHeader title={tr('CLI Agent', 'CLI 智能体')} />
        <p className='text-slate-500 text-sm mb-6 leading-relaxed max-w-xl'>
          {tr(
            'Chat runs through Reins Agent. Reins Agent Companion provides the character, voice, memory, and avatar interface.',
            '聊天由 Reins Agent 驱动。Reins Agent Companion 提供角色、语音、记忆和虚拟形象界面。',
          )}
        </p>

        <div className='grid grid-cols-1 gap-3 mb-5'>
          {ACP_AGENT_PRESET_IDS.map((id) => (
            <AgentPresetCard
              key={id}
              id={id}
              selected={agentPreset === id}
              onSelect={() => setAgentPreset(id)}
            />
          ))}
        </div>

        {agentPreset === 'custom' && (
          <>
            <label className={labelClass}>{tr('Command', '命令')}</label>
            <input
              type='text'
              value={agentProgram}
              onChange={(e) => setAgentProgram(e.target.value)}
              placeholder='e.g. python my_agent.py'
              className={inputClass}
            />
            <label className={labelClass}>
              {tr('Arguments (optional)', '参数（可选）')}
            </label>
            <input
              type='text'
              value={agentArgs}
              onChange={(e) => setAgentArgs(e.target.value)}
              placeholder='space-separated flags'
              className={inputClass}
            />
          </>
        )}

        {agentPreset !== 'custom' && (
          <div className='mb-6'>
            <AgentSetupPanel preset={presetId} />
          </div>
        )}

        <button onClick={handleSave} disabled={saving} className={buttonClass}>
          {saving
            ? tr('Saving...', '正在保存...')
            : saved
              ? tr('Saved!', '已保存！')
              : tr('Save agent', '保存智能体')}
        </button>
      </div>
    );
  }

  // ========== TTS PAGE ==========
  if (page === 'tts') {
    return (
      <div className='flex-1 overflow-y-auto p-6 scrollbar-thin scrollbar-thumb-slate-200 scrollbar-track-transparent'>
        <SubHeader title={tr('Voice & TTS', '语音与 TTS')} />
        <LocalFirstNotice
          variant={
            SETTINGS_TTS_PRESETS[ttsProvider]?.needs_key ? 'blue' : 'emerald'
          }
        />

        <label className={labelClass}>{tr('Provider', '服务提供方')}</label>
        <div className='flex flex-wrap gap-2 mb-6'>
          {Object.entries(SETTINGS_TTS_PRESETS).map(([id, preset]) => (
            <button
              key={id}
              onClick={() => setTtsProvider(id)}
              className={`px-4 py-3 rounded-2xl text-[13px] font-semibold border transition-all ${
                ttsProvider === id
                  ? 'border-blue-400 bg-blue-50 text-blue-700 shadow-sm shadow-blue-500/10 hover:-translate-y-0.5'
                  : configuredTts[id]?.configured
                    ? 'border-green-200 bg-green-50/30 text-slate-600 hover:border-green-300 hover:shadow-sm'
                    : 'border-slate-200 bg-white text-slate-500 hover:border-slate-300 hover:shadow-sm'
              }`}
            >
              <span className='flex items-center gap-1.5'>
                {tr(
                  preset.name,
                  {
                    system: '系统中文',
                    tiktok: 'Reins 语音',
                    elevenlabs: 'ElevenLabs',
                  }[id] || preset.name,
                )}
                {!preset.needs_key && (
                  <span className='text-[10px] text-emerald-600 font-bold'>
                    {tr('No key', '无需密钥')}
                  </span>
                )}
                {configuredTts[id]?.configured && ttsProvider !== id && (
                  <svg
                    className='w-3.5 h-3.5 text-green-500'
                    fill='none'
                    stroke='currentColor'
                    viewBox='0 0 24 24'
                  >
                    <path
                      strokeLinecap='round'
                      strokeLinejoin='round'
                      strokeWidth={2.5}
                      d='M5 13l4 4L19 7'
                    />
                  </svg>
                )}
              </span>
            </button>
          ))}
        </div>

        <div className='animate-in fade-in slide-in-from-bottom-2 duration-300'>
          {SETTINGS_TTS_PRESETS[ttsProvider]?.needs_key && (
            <>
              <label className={labelClass}>{tr('API Key', 'API 密钥')}</label>
              <input
                type='password'
                value={ttsApiKey}
                onChange={(e) => setTtsApiKey(e.target.value)}
                placeholder={tr(
                  'Paste your API key (blank to keep current)',
                  '粘贴 API 密钥（留空则保留当前密钥）',
                )}
                className={inputClass}
              />
            </>
          )}
          {!SETTINGS_TTS_PRESETS[ttsProvider]?.needs_key && (
            <div className='mb-5 rounded-2xl border border-emerald-100 bg-emerald-50 px-4 py-3 text-sm text-emerald-700'>
              {ttsProvider === 'system'
                ? tr(
                    'System Chinese uses Mandarin voices installed on this device.',
                    '系统中文语音使用本设备已安装的普通话声音。',
                  )
                : tr(
                    'Reins TTS is built in — no API key required.',
                    'Reins TTS 已内置，无需 API 密钥。',
                  )}
            </div>
          )}

          <label className={labelClass}>{tr('Voice', '声音')}</label>
          <div className='relative mb-8'>
            <select
              value={ttsVoice}
              onChange={(e) => setTtsVoice(e.target.value)}
              className={`${inputClass} appearance-none cursor-pointer mb-0`}
            >
              {voices.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.name}
                </option>
              ))}
            </select>
            <div className='absolute right-5 top-1/2 -translate-y-1/2 pointer-events-none text-slate-400'>
              <svg width='12' height='12' viewBox='0 0 16 16' fill='none'>
                <path
                  d='M4 6L8 10L12 6'
                  stroke='currentColor'
                  strokeWidth='2'
                  strokeLinecap='round'
                  strokeLinejoin='round'
                />
              </svg>
            </div>
          </div>

          {ttsProvider === 'system' && (
            <div className='mb-5 -mt-3'>
              <button
                type='button'
                onClick={handleSystemVoicePreview}
                disabled={voicePreviewing}
                className='flex w-full items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-blue-600 transition-colors hover:bg-slate-50 disabled:opacity-50'
              >
                <SpeakerIcon />
                {voicePreviewing
                  ? tr('Playing Mandarin…', '正在播放普通话...')
                  : tr('Preview Chinese voice', '试听中文声音')}
              </button>
              {voicePreviewError && (
                <p className='mt-2 text-xs text-red-600'>{voicePreviewError}</p>
              )}
            </div>
          )}

          <button
            onClick={handleSave}
            disabled={saving}
            className={buttonClass}
          >
            {saving
              ? tr('Saving...', '正在保存...')
              : saved
                ? tr('Saved!', '已保存！')
                : tr('Save Configuration', '保存配置')}
          </button>
        </div>
      </div>
    );
  }

  if (page === 'privacy') {
    const handleResetAll = async () => {
      if (!confirmReset) {
        setConfirmReset(true);
        setResetError(null);
        return;
      }

      setResetting(true);
      setResetError(null);
      try {
        await resetAllAppData();
        onResetAll?.();
      } catch (err) {
        console.error('Reset failed:', err);
        setResetError(
          err instanceof Error
            ? err.message
            : 'Reset failed. Please try again.',
        );
        setConfirmReset(false);
      } finally {
        setResetting(false);
      }
    };

    const handleResetOnboarding = async () => {
      setResettingOnboarding(true);
      setOnboardingResetError(null);
      try {
        await resetOnboarding();
        onResetOnboarding?.();
      } catch (err) {
        console.error('Onboarding reset failed:', err);
        setOnboardingResetError(
          err instanceof Error ? err.message : 'Could not reset onboarding.',
        );
      } finally {
        setResettingOnboarding(false);
      }
    };

    return (
      <div className='flex-1 overflow-y-auto p-6 scrollbar-thin scrollbar-thumb-slate-200 scrollbar-track-transparent'>
        <SubHeader title={tr('Local-First Privacy', '本地优先隐私')} />
        <div className='space-y-4'>
          <PrivacyCard
            title={tr('Stays on your device', '保留在本设备上')}
            items={[
              tr('Memories and chat history', '记忆与聊天记录'),
              tr('Character personality', '伙伴性格'),
              tr('Your profile', '个人资料'),
            ]}
            tone='emerald'
          />
          <PrivacyCard
            title={tr(
              'Uses the network when you choose',
              '仅在你选择时使用网络',
            )}
            items={[
              tr('Speaking (voice provider)', '语音服务'),
              tr('Your chat assistant', '聊天智能体'),
              tr('Anything that assistant does online', '智能体执行的联网操作'),
            ]}
            tone='blue'
          />
          <PrivacyCard
            title={tr('Keys & exports', '密钥与导出')}
            items={[
              tr('API keys stay in local config', 'API 密钥保存在本地配置中'),
              tr('Exports are files you control', '导出文件由你自行管理'),
            ]}
            tone='amber'
          />

          <section className='rounded-[1.75rem] border border-violet-200 bg-violet-50 px-5 py-5 text-violet-900'>
            <h3 className='text-lg font-bold'>
              {tr('Run onboarding again', '重新运行初始设置')}
            </h3>
            <p className='mt-2 text-sm leading-relaxed text-violet-800/90'>
              {tr(
                'Reopen the first-run setup to change your companion, voice, or CLI agent. Your chat history, memories, and API keys stay on this device.',
                '重新打开初始设置以更改伙伴、语音或 CLI 智能体。聊天记录、记忆和 API 密钥仍会保留在本设备上。',
              )}
            </p>
            {onboardingResetError && (
              <p className='mt-3 rounded-2xl border border-violet-300 bg-white/70 px-4 py-3 text-sm font-medium text-violet-900'>
                {onboardingResetError}
              </p>
            )}
            <button
              type='button'
              onClick={handleResetOnboarding}
              disabled={resettingOnboarding}
              className='mt-4 rounded-2xl bg-violet-600 px-5 py-3 text-sm font-semibold text-white shadow-sm shadow-violet-600/20 transition-all hover:bg-violet-700 disabled:opacity-50'
            >
              {resettingOnboarding
                ? tr('Opening onboarding…', '正在打开初始设置...')
                : tr('Run onboarding again', '重新运行初始设置')}
            </button>
          </section>

          <section className='rounded-[1.75rem] border border-red-200 bg-red-50 px-5 py-5 text-red-800'>
            <h3 className='text-lg font-bold'>
              {tr('Reset everything', '重置全部内容')}
            </h3>
            <p className='mt-2 text-sm leading-relaxed text-red-700/90'>
              {tr(
                'Deletes your profile, companions, chat history, saved memories, API keys, and settings, then returns you to onboarding. Imported Live2D and VRM models stay on disk.',
                '删除个人资料、伙伴、聊天记录、已保存记忆、API 密钥和设置，然后返回初始设置。已导入的 Live2D 与 VRM 模型会继续保留在磁盘上。',
              )}
            </p>
            {resetError && (
              <p className='mt-3 rounded-2xl border border-red-300 bg-white/70 px-4 py-3 text-sm font-medium text-red-700'>
                {resetError}
              </p>
            )}
            <div className='mt-4 flex flex-col gap-2 sm:flex-row'>
              <button
                type='button'
                onClick={handleResetAll}
                disabled={resetting}
                className='rounded-2xl bg-red-600 px-5 py-3 text-sm font-semibold text-white shadow-sm shadow-red-600/20 transition-all hover:bg-red-700 disabled:opacity-50'
              >
                {resetting
                  ? tr('Resetting...', '正在重置...')
                  : confirmReset
                    ? tr('Yes, reset everything', '确认重置全部内容')
                    : tr('Reset and start over', '重置并重新开始')}
              </button>
              {confirmReset && !resetting && (
                <button
                  type='button'
                  onClick={() => {
                    setConfirmReset(false);
                    setResetError(null);
                  }}
                  className='rounded-2xl border border-red-200 bg-white px-5 py-3 text-sm font-semibold text-red-700 transition-all hover:bg-red-100/50'
                >
                  {tr('Cancel', '取消')}
                </button>
              )}
            </div>
          </section>
        </div>
      </div>
    );
  }

  // ========== EXPRESSIONS PAGE ==========
  if (page === 'expressions') {
    return (
      <div className='flex-1 overflow-y-auto'>
        <div className='p-6 pb-0'>
          <SubHeader title={tr('Expression Mapping', '表情映射')} />
        </div>
        {modelId ? (
          <ModelSettings
            modelId={modelId}
            onPreviewExpression={onPreviewExpression || (() => {})}
            onSaved={onExpressionsSaved}
            onClose={() => setPage(null)}
          />
        ) : (
          <div className='p-6 text-sm text-slate-400'>
            No model loaded -- select a character first.
          </div>
        )}
      </div>
    );
  }

  if (page === 'memory') {
    return (
      <div className='flex-1 overflow-y-auto'>
        <div className='p-6 pb-0'>
          <SubHeader title={tr('Memory', '记忆')} />
        </div>
        <MemoryStatePanel
          characterId={characterId}
          characterName={characterName}
          onConversationCleared={onConversationCleared}
        />
      </div>
    );
  }

  if (page === 'avatar') {
    return (
      <div className='flex-1 overflow-y-auto p-6 scrollbar-thin scrollbar-thumb-slate-200 scrollbar-track-transparent'>
        <SubHeader title={tr('Avatar on screen', '屏幕形象')} />
        {avatarZoom != null &&
        avatarBackground &&
        onAvatarZoomChange &&
        onAvatarBackgroundChange ? (
          <AvatarViewportSettings
            zoom={avatarZoom}
            background={avatarBackground}
            onZoomChange={onAvatarZoomChange}
            onBackgroundChange={onAvatarBackgroundChange}
          />
        ) : (
          <p className='text-sm text-slate-400'>
            Avatar controls are not available in this view.
          </p>
        )}
      </div>
    );
  }

  return null;
}
