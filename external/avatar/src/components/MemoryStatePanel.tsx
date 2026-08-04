import { useCallback, useEffect, useMemo, useState } from "react";
import {
  getMemory,
  searchMemory,
  clearMemory,
  clearChat,
  getMemoryOverview,
  rebuildMemoryVault,
  runMemoryDream,
  migrateLegacyMemory,
  deleteMemory,
  setMemoryPinned,
  getMemorySources,
  getMemoryTopics,
  ingestMemoryNote,
  ingestMemoryTranscript,
  ingestMemoryFileDialog,
  ingestMemoryFolderDialog,
  exportMemoryZipDialog,
  importMemoryZipDialog,
} from "../api/tauri";
import type {
  DreamRun,
  MemoryRecord,
  MemorySourceRecord,
  MemoryVaultOverview,
  TopicSummary,
} from "../types";
import { useLanguage } from "../i18n/LanguageContext";

interface Props {
  characterId?: string;
  characterName: string;
  onConversationCleared?: () => void;
}

const sectionCardClass =
  "rounded-[1.75rem] border border-slate-200/70 bg-white px-5 py-5 shadow-[0_10px_30px_rgba(15,23,42,0.05)]";

type MemoryTab = "overview" | "search" | "timeline" | "sources" | "vault";

export function MemoryStatePanel({ characterId, characterName, onConversationCleared }: Props) {
  const { tr } = useLanguage();
  const [memories, setMemories] = useState<MemoryRecord[]>([]);
  const [overview, setOverview] = useState<MemoryVaultOverview | null>(null);
  const [sources, setSources] = useState<MemorySourceRecord[]>([]);
  const [topics, setTopics] = useState<TopicSummary[]>([]);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<MemoryRecord[]>([]);
  const [noteTitle, setNoteTitle] = useState("");
  const [noteBody, setNoteBody] = useState("");
  const [transcriptTitle, setTranscriptTitle] = useState("");
  const [transcriptBody, setTranscriptBody] = useState("");
  const [loading, setLoading] = useState(false);
  const [searching, setSearching] = useState(false);
  const [activeTab, setActiveTab] = useState<MemoryTab>("overview");
  const [lastDream, setLastDream] = useState<DreamRun | null>(null);
  const [statusMessage, setStatusMessage] = useState("");
  const [busyAction, setBusyAction] = useState<null | "memories" | "conversation" | "dream" | "rebuild" | "ingest" | "export" >(null);

  const refresh = useCallback(async () => {
    if (!characterId) return;
    setLoading(true);
    try {
      const [memoryData, overviewData, sourceData, topicData] = await Promise.all([
        getMemory(characterId),
        getMemoryOverview(characterId).catch(() => null),
        getMemorySources(characterId).catch(() => []),
        getMemoryTopics(characterId).catch(() => []),
      ]);
      const mems = (memoryData as MemoryRecord[]) || [];
      setMemories(mems);
      setOverview((overviewData as MemoryVaultOverview | null) || null);
      setSources((sourceData as MemorySourceRecord[]) || []);
      setTopics((topicData as TopicSummary[]) || []);
      setResults([]);
    } catch (err) {
      console.error("Memory panel refresh error:", err);
      setMemories([]);
      setResults([]);
      setOverview(null);
      setSources([]);
      setTopics([]);
    } finally {
      setLoading(false);
    }
  }, [characterId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleSearch = useCallback(async () => {
    if (!characterId || !query.trim()) {
      setResults([]);
      return;
    }
    setSearching(true);
    try {
      const data = await searchMemory(characterId, query.trim());
      setResults((data as MemoryRecord[]) || []);
    } catch (err) {
      console.error("Memory search error:", err);
      setResults([]);
    } finally {
      setSearching(false);
    }
  }, [characterId, query]);

  const clearMemories = useCallback(async () => {
    if (!characterId) return;
    setBusyAction("memories");
    try {
      await clearMemory(characterId);
      await refresh();
    } finally {
      setBusyAction(null);
    }
  }, [characterId, refresh]);

  const clearConversation = useCallback(async () => {
    if (!characterId) return;
    setBusyAction("conversation");
    try {
      await clearChat(characterId);
      await onConversationCleared?.();
    } finally {
      setBusyAction(null);
    }
  }, [characterId, onConversationCleared]);

  const groupedMemoryLabel = useMemo(() => {
    const counts = memories.reduce<Record<string, number>>((acc, item) => {
      acc[item.type] = (acc[item.type] || 0) + 1;
      return acc;
    }, {});
    return Object.entries(counts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 3)
      .map(([type, count]) => `${type} ${count}`)
      .join(" \u00B7 ");
  }, [memories]);

  const reflections = useMemo(
    () => memories.filter((memory) => memory.type === "reflections").slice(0, 8),
    [memories]
  );

  const recentTimeline = useMemo(
    () =>
      [...memories]
        .sort((a, b) => new Date(b.ts).getTime() - new Date(a.ts).getTime())
        .slice(0, 16),
    [memories]
  );

  const runDream = useCallback(async () => {
    if (!characterId) return;
    setBusyAction("dream");
    setStatusMessage("");
    try {
      const dream = (await runMemoryDream(characterId)) as DreamRun;
      setLastDream(dream);
      setStatusMessage(tr("Dream/reflection completed and written to the vault.", "梦境反思已完成并写入记忆库。"));
      await refresh();
    } catch (err) {
      console.error("Dream run error:", err);
      setStatusMessage(tr("Dream/reflection failed. Check logs for details.", "梦境反思失败，请查看日志了解详情。"));
    } finally {
      setBusyAction(null);
    }
  }, [characterId, refresh, tr]);

  const rebuildVault = useCallback(async () => {
    if (!characterId) return;
    setBusyAction("rebuild");
    setStatusMessage("");
    try {
      const path = await rebuildMemoryVault(characterId);
      setStatusMessage(tr(`Vault rebuilt at ${path}`, `记忆库已重建：${path}`));
      await refresh();
    } catch (err) {
      console.error("Vault rebuild error:", err);
      setStatusMessage(tr("Vault rebuild failed. Check logs for details.", "记忆库重建失败，请查看日志了解详情。"));
    } finally {
      setBusyAction(null);
    }
  }, [characterId, refresh, tr]);

  const handleMemoryDelete = useCallback(async (memoryId: string) => {
    if (!characterId) return;
    await deleteMemory(characterId, memoryId);
    await refresh();
  }, [characterId, refresh]);

  const handleMemoryPin = useCallback(async (memoryId: string, pinned: boolean) => {
    if (!characterId) return;
    await setMemoryPinned(characterId, memoryId, pinned);
    await refresh();
  }, [characterId, refresh]);

  const ingestNote = useCallback(async () => {
    if (!characterId || !noteTitle.trim() || !noteBody.trim()) return;
    setBusyAction("ingest");
    try {
      const count = await ingestMemoryNote(characterId, noteTitle.trim(), noteBody.trim());
      setStatusMessage(tr(
        `Imported note with ${count} memory entr${count === 1 ? "y" : "ies"}.`,
        `已从笔记导入 ${count} 条记忆。`,
      ));
      setNoteTitle("");
      setNoteBody("");
      await refresh();
    } finally {
      setBusyAction(null);
    }
  }, [characterId, noteBody, noteTitle, refresh, tr]);

  const ingestTranscript = useCallback(async () => {
    if (!characterId || !transcriptTitle.trim() || !transcriptBody.trim()) return;
    setBusyAction("ingest");
    try {
      const count = await ingestMemoryTranscript(characterId, transcriptTitle.trim(), transcriptBody.trim());
      setStatusMessage(tr(
        `Imported transcript with ${count} memory entr${count === 1 ? "y" : "ies"}.`,
        `已从会议记录导入 ${count} 条记忆。`,
      ));
      setTranscriptTitle("");
      setTranscriptBody("");
      await refresh();
    } finally {
      setBusyAction(null);
    }
  }, [characterId, transcriptBody, transcriptTitle, refresh, tr]);

  const ingestFile = useCallback(async () => {
    if (!characterId) return;
    setBusyAction("ingest");
    try {
      const count = await ingestMemoryFileDialog(characterId);
      if (count !== null) {
        setStatusMessage(tr(
          `Imported file with ${count} memory entr${count === 1 ? "y" : "ies"}.`,
          `已从文件导入 ${count} 条记忆。`,
        ));
        await refresh();
      }
    } finally {
      setBusyAction(null);
    }
  }, [characterId, refresh, tr]);

  const ingestFolder = useCallback(async () => {
    if (!characterId) return;
    setBusyAction("ingest");
    try {
      const count = await ingestMemoryFolderDialog(characterId);
      if (count !== null) {
        setStatusMessage(tr(
          `Imported folder with ${count} memory entr${count === 1 ? "y" : "ies"}.`,
          `已从文件夹导入 ${count} 条记忆。`,
        ));
        await refresh();
      }
    } finally {
      setBusyAction(null);
    }
  }, [characterId, refresh, tr]);

  const migrateLegacy = useCallback(async () => {
    if (!characterId) return;
    setBusyAction("ingest");
    try {
      const count = await migrateLegacyMemory(characterId);
      setStatusMessage(tr(
        `Migrated ${count} legacy memory entr${count === 1 ? "y" : "ies"} into SQLite.`,
        `已将 ${count} 条旧版记忆迁移到 SQLite。`,
      ));
      await refresh();
    } finally {
      setBusyAction(null);
    }
  }, [characterId, refresh, tr]);

  const exportZip = useCallback(async () => {
    if (!characterId) return;
    setBusyAction("export");
    try {
      const path = await exportMemoryZipDialog(characterId);
      if (path) setStatusMessage(tr(`Exported vault zip to ${path}`, `记忆库压缩包已导出至 ${path}`));
    } finally {
      setBusyAction(null);
    }
  }, [characterId, tr]);

  const importZip = useCallback(async () => {
    if (!characterId) return;
    setBusyAction("export");
    try {
      const count = await importMemoryZipDialog(characterId);
      if (count !== null) {
        setStatusMessage(tr(
          `Imported zip with ${count} memory entr${count === 1 ? "y" : "ies"}.`,
          `已从压缩包导入 ${count} 条记忆。`,
        ));
        await refresh();
      }
    } finally {
      setBusyAction(null);
    }
  }, [characterId, refresh, tr]);


  if (!characterId) {
    return (
      <div className="p-6 text-sm text-slate-400">
        {tr("Select a character to inspect memory.", "请选择一个角色以查看记忆。")}
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-6 scrollbar-thin scrollbar-thumb-slate-200 scrollbar-track-transparent">
      <div className="mb-6 rounded-[2rem] border border-slate-200 bg-white px-5 py-5 shadow-sm">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-[0.26em] text-slate-500">{tr("Memory Vault", "记忆库")}</div>
            <h3 className="mt-2 text-2xl font-bold tracking-tight text-slate-800">{characterName}</h3>
            <p className="mt-2 max-w-sm text-sm leading-relaxed text-slate-500">
              {tr(
                "Inspect the local memory database, Markdown vault, relationship state, and background reflections.",
                "查看本地记忆数据库、Markdown 记忆库、关系状态和后台反思。",
              )}
            </p>
          </div>
          <button
            onClick={refresh}
            disabled={loading}
            className="rounded-full border border-white/90 bg-white/90 px-4 py-2 text-[12px] font-semibold uppercase tracking-[0.22em] text-slate-600 shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-md"
          >
            {loading ? tr("Refreshing", "正在刷新") : tr("Refresh", "刷新")}
          </button>
        </div>
        {groupedMemoryLabel && (
          <div className="mt-5 rounded-2xl border border-white/80 bg-white/80 px-4 py-3 text-xs font-medium text-slate-500 shadow-sm">
            {groupedMemoryLabel}
          </div>
        )}
        <div className="mt-5 grid grid-cols-2 gap-3 md:grid-cols-6">
          <Metric label={tr("Memories", "记忆")} value={overview?.total_memories ?? memories.length} />
          <Metric label={tr("Sources", "来源")} value={overview?.total_sources ?? 0} />
          <Metric label={tr("Dreams", "梦境")} value={overview?.total_dreams ?? 0} />
          <Metric label={tr("Topics", "主题")} value={overview?.topic_count ?? topics.length} />
          <Metric label={tr("Pinned", "已置顶")} value={overview?.pinned_count ?? memories.filter((m) => m.pinned).length} />
          <Metric label={tr("Mood", "心情")} value={overview?.relationship?.mood || tr("neutral", "平静")} />
        </div>
      </div>

      <div className="mb-5 flex flex-wrap gap-2">
        {(["overview", "search", "timeline", "sources", "vault"] as MemoryTab[]).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`rounded-full px-4 py-2 text-[11px] font-semibold uppercase tracking-[0.2em] transition-all ${
              activeTab === tab
                ? "bg-slate-900 text-white shadow-md"
                : "border border-slate-200 bg-white text-slate-500 hover:-translate-y-0.5 hover:shadow-sm"
            }`}
          >
            {tr(tab, {
              overview: "概览",
              search: "搜索",
              timeline: "时间线",
              sources: "来源",
              vault: "记忆库",
            }[tab])}
          </button>
        ))}
      </div>

      {statusMessage && (
        <div className="mb-5 rounded-2xl border border-blue-100 bg-blue-50 px-4 py-3 text-sm text-blue-700">
          {statusMessage}
        </div>
      )}

      <div className="space-y-5">
        {activeTab === "overview" && (
          <>
            <section className={sectionCardClass}>
              <div className="mb-4">
                <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-500">{tr("Relationship State", "关系状态")}</div>
                <h4 className="mt-2 text-lg font-bold text-slate-800">{tr("Prompt-aware companion context", "用于对话提示的陪伴关系上下文")}</h4>
              </div>
              {overview?.relationship ? (
                <div className="grid gap-3 md:grid-cols-4">
                  <Metric label={tr("Trust", "信任")} value={`${Math.round(overview.relationship.trust * 100)}%`} />
                  <Metric label={tr("Affection", "亲密度")} value={`${Math.round(overview.relationship.affection * 100)}%`} />
                  <Metric label={tr("Energy", "活力")} value={`${Math.round(overview.relationship.energy * 100)}%`} />
                  <Metric label={tr("Mood", "心情")} value={overview.relationship.mood} />
                  <div className="rounded-2xl border border-slate-100 bg-slate-50 px-4 py-3 md:col-span-4">
                    <div className="text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-400">{tr("Summary", "摘要")}</div>
                    <p className="mt-2 text-sm text-slate-600">{overview.relationship.relationship_summary}</p>
                  </div>
                </div>
              ) : (
                <EmptyState text={tr("No relationship state yet. Chat with the companion to start building it.", "暂无关系状态。与陪伴角色聊天后会逐步建立。" )} />
              )}
            </section>

            <section className={sectionCardClass}>
              <div className="mb-4 flex items-center justify-between gap-3">
                <div>
                  <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-500">{tr("Background Dream", "后台梦境")}</div>
                  <h4 className="mt-2 text-lg font-bold text-slate-800">{tr("Reflect and consolidate", "反思与整合")}</h4>
                  <p className="mt-2 text-sm leading-relaxed text-slate-500">
                    {tr("Dream runs turn recent memories into reflections and update the Markdown vault.", "梦境会将近期记忆整理为反思，并更新 Markdown 记忆库。")}
                  </p>
                </div>
                <button
                  onClick={runDream}
                  disabled={busyAction !== null}
                  className="rounded-2xl bg-indigo-600 px-4 py-3 text-[12px] font-semibold uppercase tracking-[0.18em] text-white transition-all hover:-translate-y-0.5 hover:bg-indigo-700 disabled:opacity-50"
                >
                  {busyAction === "dream" ? tr("Dreaming", "正在整理") : tr("Run Dream", "运行梦境")}
                </button>
              </div>
              <p className="rounded-2xl border border-indigo-100 bg-indigo-50 px-4 py-3 text-sm leading-relaxed text-indigo-700">
                {lastDream?.summary || tr("No manual dream run in this panel yet.", "此面板中尚未手动运行梦境。")}
              </p>
            </section>

            <section className={sectionCardClass}>
              <div className="mb-4">
                <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-500">{tr("Reflections", "反思")}</div>
                <h4 className="mt-2 text-lg font-bold text-slate-800">{tr("Recent long-horizon notes", "近期长期反思记录")}</h4>
              </div>
              <MemoryList memories={reflections} emptyText={tr("No reflections yet. Run a dream after a few meaningful conversations.", "暂无反思。进行几次有意义的对话后再运行梦境。") } onDelete={handleMemoryDelete} onPin={handleMemoryPin} />
            </section>
          </>
        )}

        {activeTab === "search" && (
          <section className={sectionCardClass}>
          <div className="mb-4 flex items-center justify-between">
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-500">{tr("Memory Search", "记忆搜索")}</div>
              <h4 className="mt-2 text-lg font-bold text-slate-800">{tr("Probe the local archive", "查询本地记忆档案")}</h4>
            </div>
            <span className="rounded-full bg-slate-100 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">
              {memories.length} {tr("entries", "条记录")}
            </span>
          </div>

          <div className="flex gap-2">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={tr("Search for preferences, facts...", "搜索偏好、事实等...")}
              className="flex-1 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-[14px] text-slate-700 outline-none transition-all placeholder:text-slate-400 focus:border-blue-300 focus:bg-white focus:ring-2 focus:ring-blue-100"
            />
            <button
              onClick={handleSearch}
              disabled={searching}
              className="rounded-2xl bg-slate-800 px-4 py-3 text-[12px] font-semibold uppercase tracking-[0.2em] text-white transition-all hover:-translate-y-0.5 hover:bg-slate-900"
            >
              {searching ? tr("Searching", "正在搜索") : tr("Search", "搜索")}
            </button>
          </div>

          {results.length > 0 && (
            <div className="mt-4 space-y-3">
              {results.map((memory) => (
                <MemoryCard key={memory.id} memory={memory} accent onDelete={handleMemoryDelete} onPin={handleMemoryPin} />
              ))}
            </div>
          )}

          <div className="mt-5">
            <MemoryList memories={memories.slice(0, 12)} emptyText={tr("No long-term memories stored yet. Start chatting and the companion will begin writing memories locally.", "尚未存储长期记忆。开始聊天后，陪伴角色会在本地逐步记录记忆。") } onDelete={handleMemoryDelete} onPin={handleMemoryPin} />
          </div>

          <button
            onClick={clearMemories}
            disabled={busyAction !== null}
            className="mt-5 w-full rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-[13px] font-semibold uppercase tracking-[0.18em] text-rose-700 transition-all hover:bg-rose-100 disabled:opacity-50"
          >
            {busyAction === "memories" ? tr("Clearing Memories...", "正在清除记忆...") : tr("Clear Memories", "清除记忆")}
          </button>
        </section>
        )}

        {activeTab === "timeline" && (
          <section className={sectionCardClass}>
            <div className="mb-4">
              <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-500">{tr("Timeline", "时间线")}</div>
              <h4 className="mt-2 text-lg font-bold text-slate-800">{tr("Recent memory writes", "近期写入的记忆")}</h4>
            </div>
            <MemoryList memories={recentTimeline} emptyText={tr("No memory timeline yet.", "暂无记忆时间线。") } onDelete={handleMemoryDelete} onPin={handleMemoryPin} />
          </section>
        )}

        {activeTab === "sources" && (
          <>
            <section className={sectionCardClass}>
              <div className="mb-4">
                <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-500">{tr("Local Source Ingestion", "导入本地来源")}</div>
                <h4 className="mt-2 text-lg font-bold text-slate-800">{tr("Notes, transcripts, and folders", "笔记、会议记录和文件夹")}</h4>
              </div>
              <div className="grid gap-4 lg:grid-cols-2">
                <div className="space-y-3">
                  <input value={noteTitle} onChange={(e) => setNoteTitle(e.target.value)} placeholder={tr("Note title", "笔记标题")} className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none focus:border-blue-300 focus:bg-white" />
                  <textarea value={noteBody} onChange={(e) => setNoteBody(e.target.value)} placeholder={tr("Markdown or text note...", "Markdown 或文本笔记...")} rows={6} className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none focus:border-blue-300 focus:bg-white" />
                  <button onClick={ingestNote} disabled={busyAction !== null} className="w-full rounded-2xl bg-slate-900 px-4 py-3 text-[12px] font-semibold uppercase tracking-[0.18em] text-white disabled:opacity-50">{tr("Import Note", "导入笔记")}</button>
                </div>
                <div className="space-y-3">
                  <input value={transcriptTitle} onChange={(e) => setTranscriptTitle(e.target.value)} placeholder={tr("Meeting title", "会议标题")} className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none focus:border-blue-300 focus:bg-white" />
                  <textarea value={transcriptBody} onChange={(e) => setTranscriptBody(e.target.value)} placeholder={tr("Meeting transcript...", "会议记录...")} rows={6} className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none focus:border-blue-300 focus:bg-white" />
                  <button onClick={ingestTranscript} disabled={busyAction !== null} className="w-full rounded-2xl bg-indigo-600 px-4 py-3 text-[12px] font-semibold uppercase tracking-[0.18em] text-white disabled:opacity-50">{tr("Import Transcript", "导入会议记录")}</button>
                </div>
              </div>
              <div className="mt-4 grid gap-3 md:grid-cols-3">
                <button onClick={ingestFile} disabled={busyAction !== null} className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-xs font-semibold uppercase tracking-[0.18em] text-slate-600 disabled:opacity-50">{tr("Import File", "导入文件")}</button>
                <button onClick={ingestFolder} disabled={busyAction !== null} className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-xs font-semibold uppercase tracking-[0.18em] text-slate-600 disabled:opacity-50">{tr("Import Folder", "导入文件夹")}</button>
                <button onClick={migrateLegacy} disabled={busyAction !== null} className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-xs font-semibold uppercase tracking-[0.18em] text-slate-600 disabled:opacity-50">{tr("Migrate JSONL", "迁移 JSONL")}</button>
              </div>
            </section>

            <section className={sectionCardClass}>
              <div className="mb-4">
                <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-500">{tr("Source Provenance", "来源记录")}</div>
                <h4 className="mt-2 text-lg font-bold text-slate-800">{tr("Recent ingested sources", "近期导入的来源")}</h4>
              </div>
              <div className="space-y-3">
                {sources.length === 0 ? <EmptyState text={tr("No ingested sources yet.", "暂无已导入的来源。")} /> : sources.map((source) => (
                  <div key={source.id} className="rounded-2xl border border-slate-200 bg-white px-4 py-3">
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-sm font-bold text-slate-800">{source.title}</span>
                      <span className="text-[11px] text-slate-400">{new Date(source.ts).toLocaleString()}</span>
                    </div>
                    <div className="mt-2 text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">{source.source_kind}</div>
                  </div>
                ))}
              </div>
            </section>

            <section className={sectionCardClass}>
              <div className="mb-4">
                <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-500">{tr("Topics", "主题")}</div>
                <h4 className="mt-2 text-lg font-bold text-slate-800">{tr("Derived topic summaries", "自动整理的主题摘要")}</h4>
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                {topics.length === 0 ? <EmptyState text={tr("No topics yet.", "暂无主题。")} /> : topics.map((topic) => (
                  <div key={topic.topic} className="rounded-2xl border border-slate-100 bg-slate-50 px-4 py-3">
                    <div className="text-sm font-bold text-slate-800">{topic.topic}</div>
                    <div className="mt-1 text-xs text-slate-400">{topic.count} {tr("memories", "条记忆")}</div>
                    <p className="mt-2 text-sm text-slate-600">{topic.summary}</p>
                  </div>
                ))}
              </div>
            </section>
          </>
        )}

        {activeTab === "vault" && (
          <>
            <section className={sectionCardClass}>
              <div className="mb-4">
                <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-500">{tr("Markdown Vault", "Markdown 记忆库")}</div>
                <h4 className="mt-2 text-lg font-bold text-slate-800">{tr("Local readable projection", "本地可读视图")}</h4>
                <p className="mt-2 text-sm leading-relaxed text-slate-500">
                  {tr(
                    "The SQLite database is canonical. The Markdown vault is rebuilt from it for browsing, backups, and Obsidian-style workflows.",
                    "SQLite 数据库是主数据源。Markdown 记忆库由数据库重建，用于浏览、备份和 Obsidian 风格的工作流。",
                  )}
                </p>
              </div>
              <div className="space-y-3 rounded-2xl border border-slate-100 bg-slate-50 px-4 py-4">
                <PathRow label={tr("Vault folder", "记忆库文件夹")} value={overview?.vault_path || tr("Not built yet", "尚未构建")} />
                <PathRow label={tr("Database", "数据库")} value={overview?.database_path || tr("Not initialized yet", "尚未初始化")} />
                <PathRow label={tr("Latest memory", "最新记忆")} value={overview?.latest_memory_at || tr("none", "无")} />
                <PathRow label={tr("Latest dream", "最新梦境")} value={overview?.latest_dream_at || tr("none", "无")} />
              </div>
              <button
                onClick={rebuildVault}
                disabled={busyAction !== null}
                className="mt-5 w-full rounded-2xl bg-slate-900 px-4 py-3 text-[13px] font-semibold uppercase tracking-[0.18em] text-white transition-all hover:-translate-y-0.5 hover:bg-black disabled:opacity-50"
              >
                {busyAction === "rebuild" ? tr("Rebuilding Vault...", "正在重建记忆库...") : tr("Rebuild Vault", "重建记忆库")}
              </button>
              <div className="mt-3 grid gap-3 md:grid-cols-2">
                <button
                  onClick={exportZip}
                  disabled={busyAction !== null}
                  className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-[12px] font-semibold uppercase tracking-[0.18em] text-slate-600 disabled:opacity-50"
                >
                  {tr("Export Zip", "导出压缩包")}
                </button>
                <button
                  onClick={importZip}
                  disabled={busyAction !== null}
                  className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-[12px] font-semibold uppercase tracking-[0.18em] text-slate-600 disabled:opacity-50"
                >
                  {tr("Import Zip", "导入压缩包")}
                </button>
              </div>
            </section>

        <section className={`${sectionCardClass} bg-slate-50`}>
          <div className="mb-4">
            <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-500">{tr("Conversation Archive", "对话档案")}</div>
            <h4 className="mt-2 text-lg font-bold text-slate-800">{tr("Session control", "会话管理")}</h4>
            <p className="mt-2 text-sm leading-relaxed text-slate-500">
              {tr("Clear chat history to restart the conversation without deleting long-term memories.", "清除聊天记录可重新开始对话，同时保留长期记忆。")}
            </p>
          </div>
          <button
            onClick={clearConversation}
            disabled={busyAction !== null}
            className="w-full rounded-2xl bg-slate-900 px-4 py-3 text-[13px] font-semibold uppercase tracking-[0.18em] text-white transition-all hover:-translate-y-0.5 hover:bg-black disabled:opacity-50"
          >
            {busyAction === "conversation" ? tr("Clearing Conversation...", "正在清除对话...") : tr("Clear Conversation", "清除对话")}
          </button>
        </section>
          </>
        )}
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-2xl border border-white/80 bg-white/85 px-4 py-3 shadow-sm">
      <div className="text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-400">{label}</div>
      <div className="mt-1 truncate text-lg font-bold text-slate-800">{value}</div>
    </div>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="rounded-[1.5rem] border border-dashed border-slate-200 bg-slate-50 px-4 py-5 text-sm text-slate-400">
      {text}
    </div>
  );
}

function MemoryList({
  memories,
  emptyText,
  onDelete,
  onPin,
}: {
  memories: MemoryRecord[];
  emptyText: string;
  onDelete?: (memoryId: string) => void | Promise<void>;
  onPin?: (memoryId: string, pinned: boolean) => void | Promise<void>;
}) {
  if (memories.length === 0) {
    return <EmptyState text={emptyText} />;
  }
  return (
    <div className="space-y-3">
      {memories.map((memory) => (
        <MemoryCard key={memory.id} memory={memory} onDelete={onDelete} onPin={onPin} />
      ))}
    </div>
  );
}

function MemoryCard({
  memory,
  accent = false,
  onDelete,
  onPin,
}: {
  memory: MemoryRecord;
  accent?: boolean;
  onDelete?: (memoryId: string) => void | Promise<void>;
  onPin?: (memoryId: string, pinned: boolean) => void | Promise<void>;
}) {
  const { language, tr } = useLanguage();

  return (
    <div className={`rounded-[1.45rem] border px-4 py-3 shadow-sm ${
      accent ? "border-blue-100 bg-blue-50/60" : "border-slate-200/80 bg-white"
    }`}>
      <div className="flex items-center justify-between gap-3">
        <span className={`text-[11px] font-semibold uppercase tracking-[0.22em] ${
          accent ? "text-blue-600" : "text-slate-500"
        }`}>
          {memory.type}
        </span>
        <span className="text-[11px] text-slate-400">{new Date(memory.ts).toLocaleString(language === "zh-CN" ? "zh-CN" : "en")}</span>
      </div>
      <p className="mt-2 text-sm leading-relaxed text-slate-700">{memory.summary}</p>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">
          {tr("importance", "重要性")} {Math.round(memory.importance * 100)}%
        </span>
        {memory.source_kind && (
          <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">
            {memory.source_kind}
          </span>
        )}
        {memory.topic && (
          <span className="rounded-full bg-indigo-50 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-indigo-500">
            {tr("topic", "主题")} {memory.topic}
          </span>
        )}
        {memory.tags?.slice(0, 6).map((tag) => (
          <span key={`${memory.id}-${tag}`} className="rounded-full bg-slate-100 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">
            {tag}
          </span>
        ))}
      </div>
      {(onDelete || onPin) && (
        <div className="mt-3 flex gap-2">
          {onPin && (
            <button
              onClick={() => void onPin(memory.id, !memory.pinned)}
              className="rounded-full border border-slate-200 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500"
            >
              {memory.pinned ? tr("Unpin", "取消置顶") : tr("Pin", "置顶")}
            </button>
          )}
          {onDelete && (
            <button
              onClick={() => void onDelete(memory.id)}
              className="rounded-full border border-rose-200 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-rose-600"
            >
              {tr("Forget", "忘记")}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function PathRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-400">{label}</div>
      <div className="mt-1 break-all font-mono text-xs text-slate-600">{value}</div>
    </div>
  );
}
