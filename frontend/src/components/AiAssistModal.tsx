import { useState, useEffect } from "react";
import { Sparkles, Check, RefreshCw, X, AlertCircle, BookOpen, Layers } from "lucide-react";
import { api } from "@/lib/api";
import { Button, Card, Input, Spinner } from "@/components/ui";

interface AiAssistModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  companyId?: number | null;
  targetType?: "task" | "project";
  priority?: string;
  existingDescription?: string;
  existingSpecialNote?: string;
  onApply: (desc: string, note: string) => void;
  onApplyDescription?: (desc: string) => void;
  onApplySpecialNote?: (note: string) => void;
}

interface AiResponse {
  status: "READY" | "NEEDS_CONTEXT";
  missing_entity: string | null;
  prompt_question: string | null;
  suggestions: {
    description: string;
    special_note: string;
  } | null;
}

export function AiAssistModal({
  isOpen,
  onClose,
  title,
  companyId,
  targetType = "task",
  priority,
  existingDescription = "",
  existingSpecialNote = "",
  onApply,
  onApplyDescription,
  onApplySpecialNote,
}: AiAssistModalProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [res, setRes] = useState<AiResponse | null>(null);

  // Editable suggestion state
  const [suggestedDesc, setSuggestedDesc] = useState("");
  const [suggestedNote, setSuggestedNote] = useState("");
  const [appendMode, setAppendMode] = useState(false);

  // Learn entity state when context is missing
  const [entityDesc, setEntityDesc] = useState("");
  const [techStack, setTechStack] = useState("");
  const [savingEntity, setSavingEntity] = useState(false);

  const fetchRecommendations = async () => {
    if (!title || title.trim().length < 2) {
      setError("Please enter a title before using AI recommendations.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await api<AiResponse>("/ai/recommend", {
        method: "POST",
        body: {
          title: title.trim(),
          company_id: companyId ? Number(companyId) : 1,
          priority: priority || null,
          target_type: targetType,
        },
      });
      setRes(data);
      if (data.status === "READY" && data.suggestions) {
        setSuggestedDesc(data.suggestions.description);
        setSuggestedNote(data.suggestions.special_note);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to generate AI recommendations.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      setRes(null);
      setError(null);
      setEntityDesc("");
      setTechStack("");
      fetchRecommendations();
    }
  }, [isOpen, title, companyId, priority, targetType]);

  const handleLearnEntity = async () => {
    if (!entityDesc.trim() || !res?.missing_entity) return;
    setSavingEntity(true);
    setError(null);
    try {
      await api("/ai/learn-entity", {
        method: "POST",
        body: {
          company_id: companyId ? Number(companyId) : 1,
          entity_name: res.missing_entity,
          description: entityDesc.trim(),
          tech_stack: techStack.trim() || null,
        },
      });
      // Context saved! Re-fetch recommendations
      await fetchRecommendations();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to save company knowledge.");
    } finally {
      setSavingEntity(false);
    }
  };

  const handleApplyBoth = () => {
    const finalDesc = appendMode && existingDescription
      ? `${existingDescription.trim()}\n\n${suggestedDesc}`
      : suggestedDesc;
    const finalNote = appendMode && existingSpecialNote
      ? `${existingSpecialNote.trim()}\n\n${suggestedNote}`
      : suggestedNote;

    onApply(finalDesc, finalNote);
    onClose();
  };

  const handleApplyDescOnly = () => {
    const finalDesc = appendMode && existingDescription
      ? `${existingDescription.trim()}\n\n${suggestedDesc}`
      : suggestedDesc;
    if (onApplyDescription) {
      onApplyDescription(finalDesc);
    } else {
      onApply(finalDesc, existingSpecialNote);
    }
    onClose();
  };

  const handleApplyNoteOnly = () => {
    const finalNote = appendMode && existingSpecialNote
      ? `${existingSpecialNote.trim()}\n\n${suggestedNote}`
      : suggestedNote;
    if (onApplySpecialNote) {
      onApplySpecialNote(finalNote);
    } else {
      onApply(existingDescription, finalNote);
    }
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-xs">
      <Card className="w-full max-w-2xl max-h-[90vh] flex flex-col p-6 shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150">
        {/* Header */}
        <div className="flex items-center justify-between pb-3 border-b border-slate-100">
          <div className="flex items-center gap-2">
            <div className="grid h-8 w-8 place-items-center rounded-lg bg-indigo-50 text-indigo-600">
              <Sparkles className="h-4 w-4" />
            </div>
            <div>
              <h2 className="text-base font-semibold text-brand-ink">AI Assistant Recommendations</h2>
              <p className="text-xs text-slate-500">Auto-suggest Description & Special Note tailored to company context</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600 transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Content body */}
        <div className="my-4 flex-1 overflow-y-auto space-y-4 pr-1">
          {/* Title context banner */}
          <div className="rounded-lg bg-slate-50 p-3 border border-slate-200/80 text-xs text-slate-700 flex items-center justify-between">
            <span className="truncate">
              Target: <b className="capitalize">{targetType}</b> · Title: <b>"{title}"</b>
            </span>
            <Button
              variant="ghost"
              className="text-xs py-1 h-7 text-indigo-600 hover:text-indigo-700 gap-1"
              onClick={fetchRecommendations}
              disabled={loading}
            >
              <RefreshCw className={`h-3 w-3 ${loading ? "animate-spin" : ""}`} />
              Regenerate
            </Button>
          </div>

          {error && (
            <div className="flex items-start gap-2 rounded-lg bg-red-50 p-3 text-xs text-red-700 border border-red-200">
              <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {/* Loading state */}
          {loading && (
            <div className="py-12 flex flex-col items-center justify-center gap-3 text-center">
              <Spinner />
              <p className="text-sm font-medium text-slate-700">Analyzing title and company knowledge...</p>
              <p className="text-xs text-slate-400">Generating structured description and special notes</p>
            </div>
          )}

          {/* Unknown Entity Context Needed Step ("What is Elala?") */}
          {!loading && res?.status === "NEEDS_CONTEXT" && (
            <div className="rounded-xl border-2 border-indigo-200 bg-indigo-50/50 p-5 space-y-4">
              <div className="flex items-start gap-3">
                <div className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-indigo-600 text-white shadow-sm">
                  <BookOpen className="h-5 w-5" />
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-indigo-950">
                    We haven't seen "{res.missing_entity}" before
                  </h3>
                  <p className="text-xs text-indigo-800 mt-1">
                    Please provide a quick 1-line description of what <b>"{res.missing_entity}"</b> is (e.g. mobile app, internal system, client product).
                    The AI will remember it for all future tasks and projects in this company!
                  </p>
                </div>
              </div>

              <div className="space-y-3 bg-white p-4 rounded-lg border border-indigo-100 shadow-xs">
                <div>
                  <label className="text-xs font-semibold text-slate-700 block mb-1">
                    What is "{res.missing_entity}"? *
                  </label>
                  <textarea
                    rows={2}
                    className="block w-full rounded-lg border border-slate-300 px-3 py-2 text-xs focus:border-indigo-500 focus:outline-indigo-200"
                    placeholder="e.g. B2B jewelry eCommerce mobile app and admin portal"
                    value={entityDesc}
                    onChange={(e) => setEntityDesc(e.target.value)}
                  />
                </div>
                <div>
                  <label className="text-xs font-semibold text-slate-700 block mb-1">
                    Tech Stack / Details (optional)
                  </label>
                  <Input
                    className="text-xs"
                    placeholder="e.g. Flutter, Node.js, MySQL"
                    value={techStack}
                    onChange={(e) => setTechStack(e.target.value)}
                  />
                </div>
                <div className="flex justify-end pt-2">
                  <Button
                    onClick={handleLearnEntity}
                    disabled={savingEntity || !entityDesc.trim()}
                    className="gap-2 text-xs"
                  >
                    {savingEntity ? "Saving Knowledge..." : <><Check className="h-3.5 w-3.5" /> Save to Company Memory & Generate</>}
                  </Button>
                </div>
              </div>
            </div>
          )}

          {/* Ready with Suggestions */}
          {!loading && res?.status === "READY" && (
            <div className="space-y-4">
              {/* Mode toggle if text already exists */}
              {(existingDescription || existingSpecialNote) && (
                <div className="flex items-center gap-3 text-xs text-slate-600 bg-amber-50 p-2.5 rounded-lg border border-amber-200">
                  <span className="font-medium text-amber-800">Existing content detected:</span>
                  <label className="flex items-center gap-1.5 cursor-pointer">
                    <input
                      type="radio"
                      name="append_mode"
                      checked={!appendMode}
                      onChange={() => setAppendMode(false)}
                    />
                    <span>Replace existing</span>
                  </label>
                  <label className="flex items-center gap-1.5 cursor-pointer">
                    <input
                      type="radio"
                      name="append_mode"
                      checked={appendMode}
                      onChange={() => setAppendMode(true)}
                    />
                    <span>Append to existing</span>
                  </label>
                </div>
              )}

              {/* Description Suggestion */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-semibold text-slate-700 flex items-center gap-1.5">
                    <Layers className="h-3.5 w-3.5 text-indigo-600" />
                    Recommended Description (Editable)
                  </label>
                  <button
                    onClick={handleApplyDescOnly}
                    className="text-xs text-indigo-600 hover:text-indigo-800 font-medium hover:underline"
                  >
                    Insert Description only
                  </button>
                </div>
                <textarea
                  rows={6}
                  className="block w-full rounded-lg border border-slate-300 p-3 text-xs font-mono text-slate-800 focus:border-indigo-500 focus:outline-indigo-200 leading-relaxed bg-slate-50/50"
                  value={suggestedDesc}
                  onChange={(e) => setSuggestedDesc(e.target.value)}
                />
              </div>

              {/* Special Note Suggestion */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-semibold text-slate-700 flex items-center gap-1.5">
                    <Sparkles className="h-3.5 w-3.5 text-amber-500" />
                    Recommended Special Note (Editable)
                  </label>
                  <button
                    onClick={handleApplyNoteOnly}
                    className="text-xs text-indigo-600 hover:text-indigo-800 font-medium hover:underline"
                  >
                    Insert Special Note only
                  </button>
                </div>
                <textarea
                  rows={3}
                  className="block w-full rounded-lg border border-slate-300 p-3 text-xs text-slate-800 focus:border-indigo-500 focus:outline-indigo-200 leading-relaxed bg-amber-50/30"
                  value={suggestedNote}
                  onChange={(e) => setSuggestedNote(e.target.value)}
                />
              </div>
            </div>
          )}
        </div>

        {/* Footer actions */}
        <div className="pt-3 border-t border-slate-100 flex items-center justify-between">
          <Button variant="ghost" onClick={onClose} className="text-xs">
            Cancel
          </Button>
          {!loading && res?.status === "READY" && (
            <Button onClick={handleApplyBoth} className="gap-2 text-xs">
              <Sparkles className="h-3.5 w-3.5" />
              Insert Both into Form
            </Button>
          )}
        </div>
      </Card>
    </div>
  );
}
