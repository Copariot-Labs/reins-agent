import { useEffect, useMemo, useState } from "react";
import {
  createCharacter,
  getConfig,
  importLive2DModel,
  importVRMModel,
  listModels,
} from "../api/tauri";
import { buildCompanionPersonalityDraft } from "../lib/companionCharacterDraft";
import { COMPANION_VIBE_PACKS } from "../lib/companionVibes";
import { DEFAULT_TTS_VOICE } from "../lib/ttsPresets";
import type { ModelInfo } from "../types";
import { CompanionAvatarPreview } from "./onboarding/CompanionAvatarPreview";
import { ModelPicker } from "./onboarding/ModelPicker";
import { useLanguage } from "../i18n/LanguageContext";

const inputClass =
  "w-full px-5 py-3.5 rounded-2xl bg-slate-50 hover:bg-slate-100/50 text-slate-700 text-[15px] outline-none transition-all placeholder-slate-400 border border-slate-100 focus:bg-white focus:ring-2 focus:ring-blue-100 focus:border-blue-300";
const labelClass = "block text-sm font-semibold text-slate-700 tracking-wide mb-2 pl-1";

const RELATIONSHIP_OPTIONS = ["Gentle", "Teasing", "Protective", "Devoted", "Chaotic"] as const;
const SPEECH_OPTIONS = ["Poetic", "Playful", "Calm", "Sharp", "Intimate"] as const;

function defaultModelId(models: ModelInfo[]): string {
  if (models.some((m) => m.id === "haru")) return "haru";
  if (models.some((m) => m.id === "utsuwa")) return "utsuwa";
  return models[0]?.id ?? "haru";
}

export function AddCharacterModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (characterId: string) => void;
}) {
  const { tr } = useLanguage();
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [userName, setUserName] = useState("");
  const [userAbout, setUserAbout] = useState("");
  const [voice, setVoice] = useState(DEFAULT_TTS_VOICE);
  const [name, setName] = useState("");
  const [vibe, setVibe] = useState("Wise");
  const [relationshipStyle, setRelationshipStyle] = useState("Gentle");
  const [speechStyle, setSpeechStyle] = useState("Calm");
  const [modelId, setModelId] = useState("haru");
  const [personality, setPersonality] = useState("");
  const [personalityTouched, setPersonalityTouched] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [importing, setImporting] = useState<null | "live2d" | "vrm">(null);
  const [importMessage, setImportMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) return;

    getConfig()
      .then((cfg: any) => {
        setUserName(cfg.user?.name || "");
        setUserAbout(cfg.user?.about || "");
        setVoice(cfg.tts?.voice || DEFAULT_TTS_VOICE);
      })
      .catch((err) => {
        console.error("Failed to load config for character creation:", err);
      });

    listModels()
      .then((data) => {
        const availableModels = data as ModelInfo[];
        setModels(availableModels);
        if (availableModels.length > 0) {
          setModelId((current) =>
            availableModels.some((model) => model.id === current) ? current : defaultModelId(availableModels),
          );
        }
      })
      .catch((err) => {
        console.error("Failed to load models for character creation:", err);
        setModels([]);
      });

    setImportMessage("");
  }, [open]);

  const draftInput = useMemo(
    () => ({
      companionName: name,
      userName,
      userAbout,
      vibe,
      relationshipStyle,
      speechStyle,
    }),
    [name, userName, userAbout, vibe, relationshipStyle, speechStyle],
  );

  useEffect(() => {
    if (personalityTouched && personality.trim()) return;
    setPersonality(buildCompanionPersonalityDraft(draftInput));
  }, [draftInput, personalityTouched, personality]);

  const selectedModel = useMemo(
    () => models.find((model) => model.id === modelId) || null,
    [models, modelId],
  );

  const previewModel = useMemo(() => {
    if (!selectedModel) return null;
    return {
      id: selectedModel.id,
      type: selectedModel.type,
      path: selectedModel.path,
      animations: selectedModel.animations,
    };
  }, [selectedModel]);

  const selectedVibePack = COMPANION_VIBE_PACKS.find((pack) => pack.id === vibe);
  const vibeTitle = (pack: (typeof COMPANION_VIBE_PACKS)[number]) => tr(
    pack.title,
    {
      Wise: "温暖而睿智",
      Cheerful: "开朗又积极",
      Tsundere: "嘴硬心软",
      Chill: "轻松随和",
      Sassy: "机智大胆",
      Mysterious: "安静深邃",
    }[pack.id] ?? pack.title,
  );
  const vibeSubtitle = (pack: (typeof COMPANION_VIBE_PACKS)[number]) => tr(
    pack.subtitle,
    {
      Wise: "冷静、关怀、可靠",
      Cheerful: "鼓励、活泼",
      Tsundere: "先犀利，后温柔",
      Chill: "放松、踏实",
      Sassy: "俏皮、反应敏捷",
      Mysterious: "亲密、含蓄",
    }[pack.id] ?? pack.subtitle,
  );

  const selectVibePack = (packId: string) => {
    const pack = COMPANION_VIBE_PACKS.find((p) => p.id === packId);
    if (!pack) return;
    setVibe(pack.id);
    setRelationshipStyle(pack.relationship_style);
    setSpeechStyle(pack.speech_style);
  };

  const handleImportModel = async (kind: "live2d" | "vrm") => {
    setImporting(kind);
    setError("");
    setImportMessage("");

    try {
      const imported = kind === "live2d" ? await importLive2DModel() : await importVRMModel();
      if (!imported) {
        return;
      }

      const refreshed = (await listModels()) as ModelInfo[];
      setModels(refreshed);
      if (imported.id) {
        setModelId(imported.id);
        setImportMessage(
          tr(
            `Imported model "${imported.id}" and selected it.`,
            `已导入并选择模型“${imported.id}”。`,
          ),
        );
      } else {
        setImportMessage(tr('Model imported successfully.', '模型导入成功。'));
      }
    } catch (err) {
      console.error("Failed to import model:", err);
      setError(
        typeof err === "string"
          ? err
          : tr('Could not import the selected model.', '无法导入所选模型。'),
      );
    } finally {
      setImporting(null);
    }
  };

  const resetAndClose = () => {
    setName("");
    setVibe("Wise");
    setRelationshipStyle("Gentle");
    setSpeechStyle("Calm");
    setModelId("haru");
    setPersonalityTouched(false);
    setAdvancedOpen(false);
    setError("");
    onClose();
  };

  const handleCreate = async () => {
    if (!name.trim() || !personality.trim()) {
      setError(tr('Name and personality draft are required.', '必须填写名字和性格设定。'));
      return;
    }

    setSaving(true);
    setError("");

    try {
      const characterId = await createCharacter({
        name: name.trim(),
        personality: personality.trim(),
        modelId: modelId || defaultModelId(models),
        voice,
        vibe,
        relationshipStyle,
        speechStyle,
        userName,
        userAbout,
      });
      resetAndClose();
      onCreated(characterId);
    } catch (err) {
      console.error("Failed to create character:", err);
      setError(tr('Could not create the character. Please try again.', '无法创建伙伴，请重试。'));
    } finally {
      setSaving(false);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 sm:p-6">
      <div className="absolute inset-0 bg-slate-900/20 backdrop-blur-sm" onClick={resetAndClose} />
      <div className="relative z-[101] flex w-full max-w-5xl max-h-[92vh] flex-col overflow-hidden rounded-[2rem] border border-white/70 bg-white/95 shadow-[0_20px_80px_rgba(15,23,42,0.18)] ring-1 ring-slate-100/80">
        <div className="flex items-center justify-between border-b border-slate-100 bg-white px-6 py-5 shrink-0">
          <div>
            <h2 className="text-xl font-bold tracking-tight text-slate-800">
              {tr('Add Character', '添加伙伴')}
            </h2>
            <p className="mt-1 text-sm text-slate-500">
              {tr(
                'Name them, pick a look, tune personality—uses your current voice settings.',
                '设置名字、外观与性格，并使用当前语音设置。',
              )}
            </p>
          </div>
          <button
            type="button"
            onClick={resetAndClose}
            className="flex h-10 w-10 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-500 transition-all hover:-translate-y-0.5 hover:border-slate-300 hover:text-red-500"
          >
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden>
              <path d="M3 3L13 13M13 3L3 13" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto">
          <div className="grid gap-6 p-6 lg:grid-cols-[minmax(240px,340px)_1fr] lg:gap-8">
            <div className="lg:sticky lg:top-0 lg:self-start">
              <CompanionAvatarPreview
                model={previewModel}
                companionName={name}
                vibeLabel={selectedVibePack ? vibeTitle(selectedVibePack) : undefined}
              />
            </div>

            <div className="space-y-6 min-w-0">
              <div>
                <label className={labelClass}>{tr('Companion name', '伙伴名字')}</label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder={tr('What should they be called?', '想如何称呼它？')}
                  className={inputClass}
                />
              </div>

              <div>
                <label className={labelClass}>{tr('Look', '外观')}</label>
                <p className="mb-3 text-xs text-slate-500">
                  {tr('Live2D or 3D VRM—preview updates as you choose.', '选择 Live2D 或 3D VRM，预览会立即更新。')}
                </p>
                {models.length > 0 ? (
                  <ModelPicker models={models} selectedId={modelId} onSelect={setModelId} />
                ) : (
                  <div className="rounded-2xl border border-slate-100 bg-slate-50 px-5 py-4 text-sm text-slate-600">
                    {tr('No models detected yet. Import one below.', '尚未检测到模型，请在下方导入。')}
                  </div>
                )}
                <div className="mt-3 flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => handleImportModel("live2d")}
                    disabled={importing !== null}
                    className="rounded-2xl border border-slate-200 bg-white px-4 py-2 text-[13px] font-semibold text-slate-600 shadow-sm transition-all hover:border-slate-300 hover:bg-slate-50 disabled:opacity-50"
                  >
                    {importing === "live2d"
                      ? tr('Importing…', '正在导入...')
                      : tr('Import Live2D', '导入 Live2D')}
                  </button>
                  <button
                    type="button"
                    onClick={() => handleImportModel("vrm")}
                    disabled={importing !== null}
                    className="rounded-2xl border border-slate-200 bg-white px-4 py-2 text-[13px] font-semibold text-slate-600 shadow-sm transition-all hover:border-slate-300 hover:bg-slate-50 disabled:opacity-50"
                  >
                    {importing === "vrm"
                      ? tr('Importing…', '正在导入...')
                      : tr('Import VRM', '导入 VRM')}
                  </button>
                </div>
                {importMessage ? (
                  <div className="mt-3 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
                    {importMessage}
                  </div>
                ) : null}
              </div>

              <div>
                <label className={labelClass}>{tr('Personality', '性格')}</label>
                <div className="grid grid-cols-2 gap-2.5">
                  {COMPANION_VIBE_PACKS.map((pack) => {
                    const selected = vibe === pack.id;
                    return (
                      <button
                        key={pack.id}
                        type="button"
                        onClick={() => selectVibePack(pack.id)}
                        className={`flex items-center gap-2.5 rounded-2xl border px-3 py-3 text-left transition-all ${
                          selected
                            ? "border-blue-400 bg-blue-50 ring-1 ring-blue-200/80 shadow-sm"
                            : "border-slate-200 bg-white hover:border-slate-300"
                        }`}
                      >
                        <span className="text-xl">{pack.emoji}</span>
                        <div className="min-w-0">
                          <div className={`text-sm font-semibold ${selected ? "text-blue-900" : "text-slate-800"}`}>
                            {vibeTitle(pack)}
                          </div>
                          <div className={`text-xs ${selected ? "text-blue-600/85" : "text-slate-400"}`}>
                            {vibeSubtitle(pack)}
                          </div>
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="rounded-[1.4rem] border border-slate-200 bg-slate-50/60">
                <button
                  type="button"
                  onClick={() => setAdvancedOpen((v) => !v)}
                  className="flex w-full items-center justify-between px-5 py-4 text-left"
                >
                  <span className="text-sm font-semibold text-slate-700">
                    {tr('Advanced personality', '高级性格设置')}
                  </span>
                  <span className="text-xs text-slate-400">
                    {advancedOpen ? tr('Hide', '收起') : tr('Show', '展开')}
                  </span>
                </button>
                {advancedOpen ? (
                  <div className="space-y-4 border-t border-slate-200/80 px-5 pb-5 pt-4">
                    <div className="grid gap-4 sm:grid-cols-2">
                      <div>
                        <label className="mb-2 block text-xs font-semibold uppercase tracking-wide text-slate-500">
                          {tr('Relationship', '相处方式')}
                        </label>
                        <select
                          value={relationshipStyle}
                          onChange={(e) => setRelationshipStyle(e.target.value)}
                          className={`${inputClass} cursor-pointer appearance-none`}
                        >
                          {RELATIONSHIP_OPTIONS.map((opt) => (
                            <option key={opt} value={opt}>
                              {tr(
                                opt,
                                {
                                  Gentle: '温柔',
                                  Teasing: '爱开玩笑',
                                  Protective: '守护型',
                                  Devoted: '专注陪伴',
                                  Chaotic: '自由跳脱',
                                }[opt] || opt,
                              )}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <label className="mb-2 block text-xs font-semibold uppercase tracking-wide text-slate-500">
                          {tr('Speech style', '说话风格')}
                        </label>
                        <select
                          value={speechStyle}
                          onChange={(e) => setSpeechStyle(e.target.value)}
                          className={`${inputClass} cursor-pointer appearance-none`}
                        >
                          {SPEECH_OPTIONS.map((opt) => (
                            <option key={opt} value={opt}>
                              {tr(
                                opt,
                                {
                                  Poetic: '诗意',
                                  Playful: '活泼',
                                  Calm: '沉稳',
                                  Sharp: '犀利',
                                  Intimate: '亲密',
                                }[opt] || opt,
                              )}
                            </option>
                          ))}
                        </select>
                      </div>
                    </div>
                    <div>
                      <label className="mb-2 block text-xs font-semibold uppercase tracking-wide text-slate-500">
                        {tr('Personality draft', '性格设定草稿')}
                      </label>
                      <textarea
                        value={personality}
                        onChange={(e) => {
                          setPersonalityTouched(true);
                          setPersonality(e.target.value);
                        }}
                        rows={8}
                        className={`${inputClass} resize-none rounded-3xl`}
                      />
                      <button
                        type="button"
                        onClick={() => {
                          setPersonalityTouched(false);
                          setPersonality(buildCompanionPersonalityDraft(draftInput));
                        }}
                        className="mt-3 rounded-full border border-slate-200 bg-white px-4 py-2 text-[12px] font-semibold uppercase tracking-[0.18em] text-slate-600 shadow-sm transition-all hover:-translate-y-0.5"
                      >
                        {tr('Regenerate from presets', '根据预设重新生成')}
                      </button>
                    </div>
                  </div>
                ) : null}
              </div>

              {error ? (
                <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
              ) : null}
            </div>
          </div>
        </div>

        <div className="flex shrink-0 items-center justify-between gap-4 border-t border-slate-100/80 bg-white/90 px-6 py-5">
          <button
            type="button"
            onClick={resetAndClose}
            className="rounded-2xl border border-slate-200 bg-white px-6 py-3 text-[14px] font-semibold text-slate-600 shadow-sm transition-all hover:border-slate-300 hover:bg-slate-50"
          >
            {tr('Cancel', '取消')}
          </button>
          <button
            type="button"
            onClick={handleCreate}
            disabled={saving || !name.trim() || !personality.trim()}
            className="rounded-2xl bg-blue-600 px-6 py-3 text-[14px] font-semibold text-white shadow-sm transition-all hover:bg-blue-700 disabled:opacity-50"
          >
            {saving
              ? tr('Creating…', '正在创建...')
              : tr('Create character', '创建伙伴')}
          </button>
        </div>
      </div>
    </div>
  );
}
