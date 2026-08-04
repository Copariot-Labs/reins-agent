import { useEffect, useRef, useState } from 'react';
import {
  saveConfig,
  createCharacter,
  getVoices,
  previewVoice,
  listModels,
  installAgentSetup,
  type AgentSetupStatusResponse,
} from '../api/tauri';
import {
  ACP_AGENT_PRESET_IDS,
  type AcpAgentPresetId,
} from '../lib/agentPresets';
import { COMPANION_VIBE_PACKS } from '../lib/companionVibes';
import { buildCompanionPersonalityDraft } from '../lib/companionCharacterDraft';
import {
  DEFAULT_TTS_PROVIDER,
  DEFAULT_TTS_VOICE,
  TTS_PRESETS_UI,
} from '../lib/ttsPresets';
import { previewSystemChineseVoice } from '../audio/systemSpeech';
import { AgentPresetCard } from './agents/AgentPresetCard';
import { AgentSetupPanel } from './agents/AgentSetupPanel';
import { CompanionAvatarPreview } from './onboarding/CompanionAvatarPreview';
import { ModelPicker } from './onboarding/ModelPicker';
import { OnboardingShell } from './onboarding/OnboardingShell';
import { MeuxeMark } from './ui/MeuxeMark';
import { useLanguage } from '../i18n/LanguageContext';

interface Voice {
  id: string;
  name: string;
}

interface Model {
  id: string;
  type: string;
  model_file: string;
  path: string;
  animations?: { name: string; path: string }[];
}

interface FormData {
  user: { name: string; about: string };
  agent: {
    preset: AcpAgentPresetId;
    program: string;
    args: string;
  };
  tts: { provider: string; api_key: string; voice: string };
  companion: {
    name: string;
    personality: string;
    vibe: string;
    relationship_style: string;
    speech_style: string;
    model_id: string;
  };
}

const inputClass =
  'w-full px-5 py-3.5 rounded-2xl bg-slate-50 hover:bg-slate-100/50 text-slate-700 text-[15px] outline-none transition-all placeholder-slate-400 border border-slate-100 focus:bg-white focus:ring-2 focus:ring-indigo-100 focus:border-indigo-300 mb-4';
const labelClass = 'block text-sm font-semibold text-slate-700 mb-2';
const headingClass =
  'text-2xl sm:text-[1.65rem] font-bold text-slate-900 mb-1.5 tracking-tight';
const descriptionClass = 'text-slate-500 text-sm mb-5 leading-relaxed';

export function Onboarding({ onComplete }: { onComplete: () => void }) {
  const { tr } = useLanguage();
  const [step, setStep] = useState(0);
  const [voices, setVoices] = useState<Voice[]>([]);
  const [models, setModels] = useState<Model[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [agentSetup, setAgentSetup] = useState<AgentSetupStatusResponse | null>(
    null,
  );
  const [agentSetupLoading, setAgentSetupLoading] = useState(false);

  const ttsPresets = TTS_PRESETS_UI;

  const [form, setForm] = useState<FormData>({
    user: { name: '', about: '' },
    agent: {
      preset: 'reins',
      program: '',
      args: '',
    },
    tts: {
      provider: DEFAULT_TTS_PROVIDER,
      api_key: '',
      voice: DEFAULT_TTS_VOICE,
    },
    companion: {
      name: '',
      personality: '',
      vibe: 'Wise',
      relationship_style: 'Gentle',
      speech_style: 'Calm',
      model_id: 'haru',
    },
  });

  useEffect(() => {
    listModels()
      .then((data) => {
        const list = data as Model[];
        setModels(list);
        if (
          list.length > 0 &&
          !list.some((m) => m.id === form.companion.model_id)
        ) {
          setForm((prev) => ({
            ...prev,
            companion: { ...prev.companion, model_id: list[0].id },
          }));
        }
      })
      .catch(console.error);
  }, []);

  useEffect(() => {
    getVoices(form.tts.provider)
      .then((data) => {
        setVoices(data);
        if (
          data.length > 0 &&
          !data.find((v: Voice) => v.id === form.tts.voice)
        ) {
          setForm((prev) => ({
            ...prev,
            tts: { ...prev.tts, voice: data[0].id },
          }));
        }
      })
      .catch(console.error);
  }, [form.tts.provider]);

  useEffect(() => {
    if (step !== 4 || form.agent.preset === 'custom') {
      setAgentSetup(null);
      setAgentSetupLoading(false);
    }
  }, [step, form.agent.preset]);

  const handleAgentSetupStatus = (
    status: AgentSetupStatusResponse | null,
    loading: boolean,
  ) => {
    setAgentSetup(status);
    setAgentSetupLoading(loading);
  };

  const updateForm = (
    section: keyof FormData,
    field: string,
    value: string,
  ) => {
    setForm((prev) => ({
      ...prev,
      [section]: { ...prev[section], [field]: value },
    }));
  };

  const selectVibePack = (packId: string) => {
    const pack = COMPANION_VIBE_PACKS.find((p) => p.id === packId);
    if (!pack) return;
    setForm((prev) => ({
      ...prev,
      companion: {
        ...prev.companion,
        vibe: pack.id,
        relationship_style: pack.relationship_style,
        speech_style: pack.speech_style,
      },
    }));
  };

  const selectedPreviewModel =
    models.find((m) => m.id === form.companion.model_id) ?? null;
  const selectedVibePack = COMPANION_VIBE_PACKS.find(
    (p) => p.id === form.companion.vibe,
  );

  const [previewError, setPreviewError] = useState('');
  const [previewing, setPreviewing] = useState(false);

  const playSample = async () => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }
    setPreviewError('');
    setPreviewing(true);
    try {
      if (form.tts.provider === 'system') {
        await previewSystemChineseVoice(form.tts.voice);
        return;
      }
      const data = await previewVoice(
        form.tts.provider,
        form.tts.voice,
        form.tts.api_key || undefined,
      );
      if (!data || data.length === 0) {
        setPreviewError('Could not load a sample');
        return;
      }
      const blob = new Blob([new Uint8Array(data)], { type: 'audio/mp3' });
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audio.addEventListener('ended', () => URL.revokeObjectURL(url));
      audioRef.current = audio;
      await audio.play();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setPreviewError(msg || 'Preview failed');
    } finally {
      setPreviewing(false);
    }
  };

  const canProceed = (): boolean => {
    switch (step) {
      case 0:
        return true;
      case 1:
        return form.user.name.trim() !== '';
      case 2:
        return form.companion.name.trim() !== '' && form.companion.vibe !== '';
      case 3:
        return form.tts.voice !== '';
      case 4:
        if (form.agent.preset === 'custom') {
          return form.agent.program.trim() !== '';
        }
        if (agentSetupLoading) return false;
        if (agentSetup?.agent.ready) return true;
        return agentSetup?.prerequisites.node_available === true;
      default:
        return false;
    }
  };

  const stepHint = (): string | null => {
    if (
      step === 4 &&
      form.agent.preset !== 'custom' &&
      !canProceed() &&
      !agentSetupLoading
    ) {
      return 'Install Node.js above to finish setup.';
    }
    if (
      step === 4 &&
      form.agent.preset !== 'custom' &&
      !agentSetupLoading &&
      agentSetup &&
      !agentSetup.agent.ready &&
      agentSetup.prerequisites.node_available
    ) {
      return 'Finish will install the agent globally if it is not on your system yet.';
    }
    return null;
  };

  const handleFinish = async () => {
    setSubmitting(true);
    setError('');
    try {
      if (
        form.agent.preset !== 'custom' &&
        agentSetup &&
        !agentSetup.agent.ready
      ) {
        const installed = await installAgentSetup(form.agent.preset);
        setAgentSetup(installed);
        if (!installed.agent.ready) {
          setError(
            installed.agent.detail ||
              'Could not install the agent CLI. Try Install above, then finish again.',
          );
          setSubmitting(false);
          return;
        }
      }

      const charId = await createCharacter({
        name: form.companion.name,
        personality: buildCompanionPersonalityDraft({
          companionName: form.companion.name,
          userName: form.user.name,
          userAbout: form.user.about,
          vibe: form.companion.vibe,
          relationshipStyle: form.companion.relationship_style,
          speechStyle: form.companion.speech_style,
        }),
        modelId: form.companion.model_id,
        voice: form.tts.voice,
        vibe: form.companion.vibe,
        relationshipStyle: form.companion.relationship_style,
        speechStyle: form.companion.speech_style,
        userName: form.user.name,
        userAbout: form.user.about,
      });

      await saveConfig({
        user: form.user,
        agent: {
          preset: form.agent.preset,
          program: form.agent.program,
          args: form.agent.args.trim()
            ? form.agent.args.trim().split(/\s+/)
            : [],
        },
        tts: {
          provider: form.tts.provider,
          api_key: form.tts.api_key || null,
          voice: form.tts.voice,
        },
        active_character: charId,
        onboarding_complete: true,
      });

      setStep(5);
      setTimeout(onComplete, 2200);
    } catch {
      setError('Something went wrong. Please try again.');
    }
    setSubmitting(false);
  };

  const preview = (
    <CompanionAvatarPreview
      model={selectedPreviewModel}
      companionName={form.companion.name}
      vibeLabel={selectedVibePack?.title}
    />
  );

  if (step === 5) {
    return (
      <OnboardingShell step={step}>
        <div className='text-center py-8 animate-in fade-in zoom-in-95 duration-500'>
          <MeuxeMark className='h-16 w-16 mx-auto mb-5' />
          <h2 className='text-2xl font-bold text-slate-900 mb-2'>
            {tr("You're all set", '设置完成')}
          </h2>
          <p className='text-slate-500 text-[15px] max-w-sm mx-auto'>
            <span className='font-semibold text-indigo-600'>
              {form.companion.name}
            </span>{' '}
            {tr('is waiting on your desktop.', '已经在桌面上等你了。')}
          </p>
        </div>
      </OnboardingShell>
    );
  }

  return (
    <OnboardingShell step={step} preview={preview}>
      {step === 0 && (
        <div className='animate-in fade-in duration-500'>
          <h2 className={headingClass}>
            {tr('A companion for Reins Agent', '为 Reins Agent 创建伙伴')}
          </h2>
          <p className={descriptionClass}>
            {tr(
              'Talk to someone who remembers you. They live on your computer—not in a generic chat app.',
              '与你熟悉并记得你的伙伴交流。它生活在你的电脑里，而不是普通聊天应用中。',
            )}
          </p>
          <div className='grid gap-3 sm:grid-cols-3'>
            {[
              {
                emoji: '💬',
                title: tr('Real conversations', '真实对话'),
                sub: tr('They grow with you', '与你一同成长'),
              },
              {
                emoji: '🎭',
                title: tr('Face & voice', '形象与声音'),
                sub: tr('See them react', '看到它的回应'),
              },
              {
                emoji: '🔒',
                title: tr('Your device', '你的设备'),
                sub: tr('Memories stay local', '记忆保留在本地'),
              },
            ].map((f) => (
              <div
                key={f.title}
                className='flex items-center gap-3 rounded-2xl border border-slate-100 bg-slate-50/90 px-4 py-3.5'
              >
                <span className='text-2xl'>{f.emoji}</span>
                <div>
                  <div className='text-sm font-semibold text-slate-800'>
                    {f.title}
                  </div>
                  <div className='text-xs text-slate-500'>{f.sub}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {step === 1 && (
        <div className='animate-in fade-in duration-500'>
          <h2 className={headingClass}>{tr('First, your name', '首先，请告诉我你的名字')}</h2>
          <p className={descriptionClass}>
            {tr(
              "So they know who they're talking to. Only saved on this device.",
              '让伙伴知道正在与谁交谈。信息只会保存在本设备上。',
            )}
          </p>
          <label className={labelClass}>{tr('Name', '名字')}</label>
          <input
            type='text'
            value={form.user.name}
            onChange={(e) => updateForm('user', 'name', e.target.value)}
            placeholder={tr('e.g. Alex', '例如：小林')}
            className={inputClass}
            autoFocus
          />
          <label className={labelClass}>
            {tr('Anything they should know', '希望伙伴了解的事情')}{' '}
            <span className='font-normal text-slate-400'>
              {tr('(optional)', '（可选）')}
            </span>
          </label>
          <textarea
            value={form.user.about}
            onChange={(e) => updateForm('user', 'about', e.target.value)}
            placeholder={tr('A line or two about you…', '用一两句话介绍自己...')}
            rows={2}
            className={`${inputClass} resize-none rounded-2xl mb-0`}
          />
        </div>
      )}

      {step === 2 && (
        <div className='animate-in fade-in duration-500'>
          <h2 className={headingClass}>{tr('Meet them', '认识你的伙伴')}</h2>
          <p className={descriptionClass}>
            {tr('Name, look, and personality—in one place.', '在这里设置名字、外观和性格。')}
          </p>

          <label className={labelClass}>{tr('Their name', '伙伴的名字')}</label>
          <input
            type='text'
            value={form.companion.name}
            onChange={(e) => updateForm('companion', 'name', e.target.value)}
            placeholder={tr('Who are you creating?', '想为伙伴取什么名字？')}
            className={inputClass}
          />

          <label className={labelClass}>{tr('Personality', '性格')}</label>
          <div className='grid grid-cols-2 gap-2.5 mb-5'>
            {COMPANION_VIBE_PACKS.map((pack) => {
              const selected = form.companion.vibe === pack.id;
              return (
                <button
                  key={pack.id}
                  type='button'
                  onClick={() => selectVibePack(pack.id)}
                  className={`flex items-center gap-2.5 rounded-2xl border px-3 py-3 text-left transition-all ${
                    selected
                      ? 'border-indigo-400 bg-indigo-50 ring-1 ring-indigo-200/80 shadow-sm'
                      : 'border-slate-200 bg-white hover:border-slate-300'
                  }`}
                >
                  <span className='text-xl'>{pack.emoji}</span>
                  <div className='min-w-0'>
                    <div
                      className={`text-sm font-semibold ${selected ? 'text-indigo-900' : 'text-slate-800'}`}
                    >
                      {tr(
                        pack.title,
                        {
                          Wise: '温暖而睿智',
                          Cheerful: '开朗又积极',
                          Tsundere: '嘴硬心软',
                          Chill: '轻松随和',
                          Sassy: '机智大胆',
                          Mysterious: '安静深邃',
                        }[pack.id] || pack.title,
                      )}
                    </div>
                    <div
                      className={`text-xs ${selected ? 'text-indigo-600/85' : 'text-slate-400'}`}
                    >
                      {tr(
                        pack.subtitle,
                        {
                          Wise: '冷静、关怀、可靠',
                          Cheerful: '鼓励、活泼',
                          Tsundere: '先犀利，后温柔',
                          Chill: '放松、踏实',
                          Sassy: '俏皮、反应敏捷',
                          Mysterious: '亲密、含蓄',
                        }[pack.id] || pack.subtitle,
                      )}
                    </div>
                  </div>
                </button>
              );
            })}
          </div>

          <label className={labelClass}>{tr('Look', '外观')}</label>
          <ModelPicker
            models={models}
            selectedId={form.companion.model_id}
            onSelect={(id) => updateForm('companion', 'model_id', id)}
          />
        </div>
      )}

      {step === 3 && (
        <div className='animate-in fade-in duration-500'>
          <h2 className={headingClass}>{tr('How they sound', '选择伙伴的声音')}</h2>
          <p className={descriptionClass}>
            {tr('Pick a voice and tap listen.', '选择声音并点击试听。')}
          </p>

          <div className='grid gap-2.5 mb-5 sm:grid-cols-3'>
            {Object.entries(ttsPresets).map(([id, preset]) => {
              const selected = form.tts.provider === id;
              return (
                <button
                  key={id}
                  type='button'
                  onClick={() => updateForm('tts', 'provider', id)}
                  className={`rounded-2xl border px-4 py-3 text-left transition-all ${
                    selected
                      ? 'border-indigo-400 bg-indigo-50 shadow-sm ring-1 ring-indigo-200/70'
                      : 'border-slate-200 bg-white hover:border-slate-300'
                  }`}
                >
                  <div
                    className={`text-sm font-semibold ${selected ? 'text-indigo-900' : 'text-slate-800'}`}
                  >
                    {tr(
                      preset.name,
                      {
                        system: '系统中文',
                        tiktok: 'Reins 语音',
                        elevenlabs: 'ElevenLabs',
                        openai_tts: 'OpenAI 语音',
                      }[id] || preset.name,
                    )}
                  </div>
                  <div
                    className={`text-xs mt-0.5 ${selected ? 'text-indigo-600/80' : 'text-slate-400'}`}
                  >
                    {tr(
                      ttsPresets[id]?.hint || '',
                      {
                        system: '使用本设备普通话声音，无需密钥',
                        tiktok: 'Reins 内置，无需密钥',
                        elevenlabs: '录音室级声音，需要 API 密钥',
                        openai_tts: 'OpenAI 语音，需要 API 密钥',
                      }[id] || ttsPresets[id]?.hint || '',
                    )}
                  </div>
                </button>
              );
            })}
          </div>

          {ttsPresets[form.tts.provider]?.needs_key && (
            <>
              <label className={labelClass}>{tr('API key', 'API 密钥')}</label>
              <input
                type='password'
                value={form.tts.api_key}
                onChange={(e) => updateForm('tts', 'api_key', e.target.value)}
                placeholder={tr('Paste key from your provider', '粘贴服务提供方的密钥')}
                className={inputClass}
              />
            </>
          )}

          <label className={labelClass}>{tr('Voice', '声音')}</label>
          <div className='flex flex-col gap-2 sm:flex-row sm:items-start'>
            <div className='relative flex-1'>
              <select
                value={form.tts.voice}
                onChange={(e) => updateForm('tts', 'voice', e.target.value)}
                className={`${inputClass} appearance-none cursor-pointer mb-0`}
              >
                {voices.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.name}
                  </option>
                ))}
              </select>
            </div>
            <button
              type='button'
              onClick={playSample}
              disabled={previewing}
              className='shrink-0 rounded-2xl border border-slate-200 bg-white px-5 py-3.5 text-sm font-semibold text-indigo-600 shadow-sm hover:bg-slate-50 disabled:opacity-50'
            >
              {previewing ? tr('Loading…', '正在加载...') : tr('Listen', '试听')}
            </button>
          </div>
          {previewError && (
            <p className='mt-2 text-xs text-red-600'>{previewError}</p>
          )}
        </div>
      )}

      {step === 4 && (
        <div className='animate-in fade-in duration-500'>
          <h2 className={headingClass}>{tr('Who answers for them?', '由谁驱动对话？')}</h2>
          <p className={descriptionClass}>
            {tr(
              'Reins is the face and memory. Choose the assistant on your computer that powers chat.',
              'Reins 提供形象与记忆。选择电脑上用于驱动聊天的智能体。',
            )}
          </p>

          <div className='grid grid-cols-1 gap-3 mb-4'>
            {ACP_AGENT_PRESET_IDS.map((id) => (
              <AgentPresetCard
                key={id}
                id={id}
                selected={form.agent.preset === id}
                onSelect={() =>
                  setForm((prev) => ({
                    ...prev,
                    agent: { ...prev.agent, preset: id },
                  }))
                }
              />
            ))}
          </div>

          {form.agent.preset === 'custom' && (
            <>
              <label className={labelClass}>{tr('Program to run', '运行程序')}</label>
              <input
                type='text'
                value={form.agent.program}
                onChange={(e) =>
                  setForm((prev) => ({
                    ...prev,
                    agent: { ...prev.agent, program: e.target.value },
                  }))
                }
                placeholder='Path or command'
                className={inputClass}
              />
              <label className={labelClass}>{tr('Extra options (optional)', '其他选项（可选）')}</label>
              <input
                type='text'
                value={form.agent.args}
                onChange={(e) =>
                  setForm((prev) => ({
                    ...prev,
                    agent: { ...prev.agent, args: e.target.value },
                  }))
                }
                placeholder='Optional flags'
                className={inputClass}
              />
            </>
          )}

          {form.agent.preset !== 'custom' && (
            <AgentSetupPanel
              preset={form.agent.preset}
              onStatusChange={handleAgentSetupStatus}
              friendly
            />
          )}
        </div>
      )}

      {error && (
        <div className='mt-4 rounded-xl border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-700'>
          {error}
        </div>
      )}

      <div className='mt-8 flex gap-3'>
        <button
          type='button'
          onClick={() => setStep(step - 1)}
          disabled={step === 0}
          className={`rounded-2xl border border-slate-200 bg-white px-5 py-3 text-sm font-medium text-slate-600 shadow-sm transition-all ${
            step === 0
              ? 'opacity-0 pointer-events-none w-0 px-0 border-0'
              : 'hover:bg-slate-50'
          }`}
        >
          {tr('Back', '返回')}
        </button>
        {step < 4 ? (
          <button
            type='button'
            onClick={() => setStep(step + 1)}
            disabled={!canProceed()}
            className='flex-1 rounded-2xl bg-indigo-600 py-3.5 text-[15px] font-semibold text-white shadow-md shadow-indigo-600/25 hover:bg-indigo-700 disabled:opacity-40'
          >
            {tr('Continue', '继续')}
          </button>
        ) : (
          <button
            type='button'
            onClick={handleFinish}
            disabled={!canProceed() || submitting}
            className='flex-1 rounded-2xl bg-indigo-600 py-3.5 text-[15px] font-semibold text-white shadow-md shadow-indigo-600/25 hover:bg-indigo-700 disabled:opacity-40'
          >
            {submitting ? tr('Creating…', '正在创建...') : tr('Finish', '完成')}
          </button>
        )}
      </div>
      {stepHint() && (
        <p className='mt-3 text-center text-xs text-slate-500'>{stepHint()}</p>
      )}
    </OnboardingShell>
  );
}
