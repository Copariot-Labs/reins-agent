import { BG_PRESETS } from "../../constants/bgPresets";
import { useLanguage } from "../../i18n/LanguageContext";

const STAGE_BACKGROUNDS = [
  { name: "Transparent (match app)", value: "transparent" },
  { name: "Light", value: "#f8fafc" },
  ...BG_PRESETS,
];

export function AvatarViewportSettings({
  zoom,
  background,
  onZoomChange,
  onBackgroundChange,
}: {
  zoom: number;
  background: string;
  onZoomChange: (zoom: number) => void;
  onBackgroundChange: (bg: string) => void;
}) {
  const { tr } = useLanguage();
  const pct = Math.round(zoom * 100);

  const backgroundName = (name: string) => {
    const names: Record<string, string> = {
      "Transparent (match app)": "透明（跟随应用）",
      Light: "浅色",
      "Warm Sunset": "暖色夕阳",
      "Cozy Room": "温馨房间",
      "Cherry Blossom": "樱花",
      "Forest Night": "森林夜色",
      "Ocean Dusk": "海洋黄昏",
      Midnight: "午夜",
    };
    return tr(name, names[name] ?? name);
  };

  return (
    <div className="space-y-6">
      <p className="text-sm text-slate-500 leading-relaxed">
        {tr("Adjust zoom and background on the main screen. Use the", "调整主界面的缩放和背景。使用设置图标下方的")} <span className="font-semibold text-slate-600">{tr("FULL / HALF", "全身 / 半身")}</span> {tr("button below the settings icon for framing.", "按钮调整取景范围。")}
      </p>

      <section className="rounded-2xl border border-slate-100 bg-white p-5 shadow-sm">
        <h3 className="text-sm font-semibold text-slate-800">{tr("Zoom", "缩放")}</h3>
        <div className="mt-3 flex items-center gap-3">
          <button
            type="button"
            onClick={() => onZoomChange(Math.round(Math.max(30, pct - 5)) / 100)}
            className="flex h-10 w-10 items-center justify-center rounded-xl border border-slate-200 bg-slate-50 text-slate-700 hover:bg-slate-100"
            aria-label={tr("Zoom out", "缩小")}
          >
            −
          </button>
          <span className="min-w-[4rem] text-center text-lg font-bold text-slate-800">{pct}%</span>
          <button
            type="button"
            onClick={() => onZoomChange(Math.round(Math.min(200, pct + 5)) / 100)}
            className="flex h-10 w-10 items-center justify-center rounded-xl border border-slate-200 bg-slate-50 text-slate-700 hover:bg-slate-100"
            aria-label={tr("Zoom in", "放大")}
          >
            +
          </button>
        </div>
      </section>

      <section className="rounded-2xl border border-slate-100 bg-white p-5 shadow-sm">
        <h3 className="text-sm font-semibold text-slate-800">{tr("Background behind avatar", "虚拟形象背景")}</h3>
        <div className="mt-3 grid gap-2">
          {STAGE_BACKGROUNDS.map((preset) => (
            <button
              key={preset.name}
              type="button"
              onClick={() => onBackgroundChange(preset.value)}
              className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm transition-all ${
                background === preset.value
                  ? "bg-blue-50 text-blue-800 ring-1 ring-blue-200"
                  : "text-slate-600 hover:bg-slate-50"
              }`}
            >
              <div
                className="h-8 w-8 shrink-0 rounded-lg ring-1 ring-slate-200/80"
                style={{
                  background: preset.value === "transparent" ? "#f1f5f9" : preset.value,
                }}
              />
              {backgroundName(preset.name)}
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}
