import { useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";
import { ArrowLeft, Beaker, BookOpen, CalendarDays, Check, ChevronRight, Leaf, ListTodo, LockKeyhole, MessageCircle, PackageOpen, Plus, RefreshCw, Search, Send, Sparkles, Sprout, Trash2, Trophy, UsersRound, Wheat, X, Zap } from "lucide-react";

import { DisabledActionReason, disabledActionTitle } from "../DisabledActionReason";
import { HelpDisclosure } from "../HelpDisclosure";
import { errorMessage, formatDate, todayString } from "../formatters";
import { ActivityIndicator, InlineLoading } from "../LoadingState";
import { ModalDialog } from "../ModalDialog";
import { SearchableSelect } from "../SearchableSelect";
import type {
  FertilizerApplication,
  FertilizerMaterial,
  FertilizerMaterialKind,
  PlantActionCompletionPayload,
  PlantActionMutationPayload,
  PlantActionReviewPayload,
  PlantActionSkipPayload,
  PlantBundle,
  PlantCalendar,
  PlantCalendarAction,
  PlantQuestionRecord,
} from "../types";
import { AnnualCalendarGantt } from "./AnnualCalendarGantt";
import { CalendarActionCard, CalendarActionPreview, CalendarKanbanCard, NewCalendarActionForm } from "./CalendarActionCard";
import { FALLBACK_ACTION_TYPES } from "./constants";

type KanbanColumn = "planned" | "in_progress" | "awaiting_review" | "completed";
type AssignmentScope = "recommended" | "all" | "mine" | "unassigned" | `member:${string}`;
type ActionTimingState = PlantBundle["suggestions"][number]["timing_state"];
type RegenerationDecision = "approved" | "rejected";
type CalendarOperation = "regenerate" | "review-decisions" | "question";

const KANBAN_COLUMNS: Array<{ id: KanbanColumn; label: string; description: string }> = [
  { id: "planned", label: "未完了", description: "着手を待っている作業" },
  { id: "in_progress", label: "作業中", description: "現在取り組んでいる作業" },
  { id: "awaiting_review", label: "確認待ち", description: "作業者が実績を提出し、管理者の確認を待っている作業" },
  { id: "completed", label: "完了・見送り", description: "実施済み、または確認して不要と判断した作業" },
];

const TIMING_SORT_ORDER: Record<ActionTimingState, number> = { overdue: 0, due: 1, upcoming: 2 };
const PRIORITY_SORT_ORDER: Record<PlantCalendarAction["priority"], number> = { required: 0, should: 1, recommended: 2, optional: 3 };
const QUESTION_HISTORY_PAGE_SIZE = 5;

function initialCalendarQueryState() {
  if (typeof window === "undefined") return { workspace: "work" as const, openAiReview: false };
  const query = new URLSearchParams(window.location.search);
  const openAiReview = query.get("review") === "ai";
  return {
    workspace: query.get("view") === "crop" || openAiReview ? "crop" as const : "work" as const,
    openAiReview,
  };
}

interface MemberTaskSummary {
  email: string;
  approvedCount: number;
  pendingCount: number;
  latestApprovedOn: string;
}


export interface PlantCalendarDrawerProps {
  bundle: PlantBundle;
  selectedPlantingId: string;
  busy: boolean;
  initialActionId?: string;
  presentation?: "modal" | "page";
  fieldName?: string;
  fieldDetailUrl?: string;
  onPlantingChange: (plantingId: string) => void;
  onClose: () => void;
  onEditAction: (plantingId: string, actionId: string, payload: PlantActionMutationPayload & { use_as_guidance?: boolean }) => Promise<void>;
  onCompleteAction: (plantingId: string, actionId: string, payload: PlantActionCompletionPayload) => Promise<void>;
  onReviewAction: (plantingId: string, actionId: string, payload: PlantActionReviewPayload) => Promise<void>;
  onSkipAction: (plantingId: string, actionId: string, payload: PlantActionSkipPayload) => Promise<void>;
  onAskQuestion: (plantingId: string, question: string) => Promise<PlantQuestionRecord>;
  onListQuestions: (plantingId: string, options?: { query?: string; page?: number; pageSize?: number; signal?: AbortSignal }) => Promise<{ items: PlantQuestionRecord[]; total: number }>;
  onRegenerate: (plantingId: string, startDate: string, planningNotes: string, mode: "automatic" | "review") => Promise<void>;
  onDecideRegeneration: (
    plantingId: string,
    taskId: string,
    decisions: Array<{ proposal_id: string; decision: RegenerationDecision }>,
  ) => Promise<void>;
  onAddAction: (plantingId: string, payload: PlantActionMutationPayload) => Promise<void>;
  onDeleteAction: (plantingId: string, actionId: string) => Promise<void>;
  onAddFertilizer: (plantingId: string, payload: Record<string, unknown>) => Promise<void>;
  onDeleteFertilizer: (plantingId: string, applicationId: string) => Promise<void>;
  onSaveFertilizerMaterial: (materialId: string, payload: Record<string, unknown>) => Promise<void>;
  onDeleteFertilizerMaterial: (materialId: string) => Promise<void>;
}

export function PlantCalendarDrawer({
  bundle,
  selectedPlantingId,
  busy,
  initialActionId = "",
  presentation = "modal",
  fieldName = "",
  fieldDetailUrl = "/fields",
  onPlantingChange,
  onClose,
  onEditAction,
  onCompleteAction,
  onReviewAction,
  onSkipAction,
  onAskQuestion,
  onListQuestions,
  onRegenerate,
  onDecideRegeneration,
  onAddAction,
  onDeleteAction,
  onAddFertilizer,
  onDeleteFertilizer,
  onSaveFertilizerMaterial,
  onDeleteFertilizerMaterial,
}: PlantCalendarDrawerProps) {
  const activePlantings = bundle.plantings.filter((planting) => planting.status === "active");
  const planting = activePlantings.find((item) => item.id === selectedPlantingId) ?? activePlantings[0] ?? null;
  const calendar = planting ? bundle.calendars[planting.id] : null;
  const generationTask = planting ? bundle.generation_tasks.find((task) => task.planting_id === planting.id) ?? null : null;
  const generationActive = generationTask?.status === "queued" || generationTask?.status === "running";
  const generationReviewPending = generationTask?.status === "awaiting_review";
  const generationLockTasks = bundle.generation_tasks.filter((task) => task.status === "queued" || task.status === "running");
  const generationLockActive = generationLockTasks.length > 0;
  const calendarMutationBusy = busy || generationLockActive;
  const initialQueryState = useRef(initialCalendarQueryState());
  const initialAiReviewRequested = useRef(initialQueryState.current.openAiReview);
  const [question, setQuestion] = useState("");
  const [questionHistory, setQuestionHistory] = useState<PlantQuestionRecord[]>([]);
  const [questionHistoryTotal, setQuestionHistoryTotal] = useState(0);
  const [questionHistoryPage, setQuestionHistoryPage] = useState(1);
  const [questionSearch, setQuestionSearch] = useState("");
  const [questionHistoryLoading, setQuestionHistoryLoading] = useState(false);
  const [questionHistoryLoadingMore, setQuestionHistoryLoadingMore] = useState(false);
  const [questionError, setQuestionError] = useState("");
  const [activeOperation, setActiveOperation] = useState<CalendarOperation | null>(null);
  const [generationOpen, setGenerationOpen] = useState(false);
  const [generationStart, setGenerationStart] = useState(todayString());
  const [generationNotes, setGenerationNotes] = useState("");
  const [generationMode, setGenerationMode] = useState<"automatic" | "review">("review");
  const [generationError, setGenerationError] = useState("");
  const [regenerationDecisions, setRegenerationDecisions] = useState<Record<string, RegenerationDecision>>({});
  const [regenerationReviewOpen, setRegenerationReviewOpen] = useState(false);
  const [activeRegenerationProposalId, setActiveRegenerationProposalId] = useState<string | null>(null);
  const [workspace, setWorkspace] = useState<"work" | "crop">(initialQueryState.current.workspace);
  const [workScopePlantingId, setWorkScopePlantingId] = useState("all");
  const [assignmentScope, setAssignmentScope] = useState<AssignmentScope>("recommended");
  const [workDate, setWorkDate] = useState("");
  const [addingAction, setAddingAction] = useState(false);
  const [newActionPlantingId, setNewActionPlantingId] = useState(selectedPlantingId);
  const [selectedActionId, setSelectedActionId] = useState<string | null>(null);
  const [recordActionId, setRecordActionId] = useState<string | null>(null);
  const [actionQuery, setActionQuery] = useState("");
  const [draggedActionId, setDraggedActionId] = useState<string | null>(null);
  const [dragOverColumn, setDragOverColumn] = useState<KanbanColumn | null>(null);
  const [dropMessage, setDropMessage] = useState("");
  const consumedInitialActionId = useRef("");
  const chatHistoryRef = useRef<HTMLDivElement | null>(null);
  const questionHistoryPointerScrollRef = useRef(false);
  const questionHistoryTouchYRef = useRef<number | null>(null);
  const questionHistoryLoadingMoreRef = useRef(false);
  const questionHistoryLoadMoreControllerRef = useRef<AbortController | null>(null);
  const questionHistoryQueryRef = useRef("");
  const pendingRegenerationProposals = (generationTask?.proposals ?? []).filter((proposal) => proposal.decision === "pending");
  const pendingRegenerationProposalKey = pendingRegenerationProposals.map((proposal) => proposal.id).join("|");
  const approvedRegenerationCount = pendingRegenerationProposals.filter((proposal) => regenerationDecisions[proposal.id] === "approved").length;
  const rejectedRegenerationCount = pendingRegenerationProposals.filter((proposal) => regenerationDecisions[proposal.id] === "rejected").length;
  const undecidedRegenerationCount = pendingRegenerationProposals.length - approvedRegenerationCount - rejectedRegenerationCount;
  const activeRegenerationProposal = activeRegenerationProposalId
    ? pendingRegenerationProposals.find((proposal) => proposal.id === activeRegenerationProposalId) ?? null
    : null;
  const activeRegenerationProposalIndex = activeRegenerationProposal
    ? pendingRegenerationProposals.findIndex((proposal) => proposal.id === activeRegenerationProposal.id)
    : -1;
  const regenerationBlockingReasons = [
    ...(!generationStart ? ["計画開始日を選択してください"] : []),
    ...(generationActive ? ["AI計画を作成中です"] : []),
    ...(generationReviewPending ? ["前回のAI変更案を確認してください"] : []),
    ...(busy ? ["現在のAI処理が完了するまでお待ちください"] : []),
  ];
  const questionBlockingReasons = [
    ...(!question.trim() ? ["質問を入力してください"] : []),
    ...(busy ? ["現在のAI処理が完了するまでお待ちください"] : []),
  ];
  const operationMessage = activeOperation === "regenerate"
    ? "AIが変更案を組み立てています"
    : activeOperation === "review-decisions"
      ? "確認結果を栽培カレンダーへ反映しています"
      : activeOperation === "question"
        ? "栽培データをもとに回答を考えています"
        : "変更を安全に反映しています";

  useEffect(() => {
    if (planting && planting.id !== selectedPlantingId) onPlantingChange(planting.id);
  }, [planting, selectedPlantingId, onPlantingChange]);

  useEffect(() => {
    setQuestionError("");
    setGenerationOpen(false);
    const planning = calendarPlanningContext(calendar);
    setGenerationStart(typeof planning.start_date === "string" ? planning.start_date : todayString());
    setGenerationNotes(typeof planning.notes === "string" ? planning.notes : "");
  }, [planting?.id, calendar?.updated_at]);

  useEffect(() => {
    if (!planting) return undefined;
    const controller = new AbortController();
    const query = questionSearch.trim();
    const delay = query ? 250 : 0;
    setQuestionHistory([]);
    setQuestionHistoryTotal(0);
    setQuestionHistoryPage(1);
    setQuestionHistoryLoading(true);
    setQuestionHistoryLoadingMore(false);
    questionHistoryLoadingMoreRef.current = false;
    questionHistoryLoadMoreControllerRef.current?.abort();
    questionHistoryLoadMoreControllerRef.current = null;
    setQuestionError("");
    const timer = window.setTimeout(() => {
      void onListQuestions(planting.id, { query, page: 1, pageSize: QUESTION_HISTORY_PAGE_SIZE, signal: controller.signal })
        .then((result) => {
          questionHistoryQueryRef.current = query;
          setQuestionHistory(result.items);
          setQuestionHistoryTotal(result.total);
          window.requestAnimationFrame(() => {
            const history = chatHistoryRef.current;
            if (history) history.scrollTop = history.scrollHeight;
          });
        })
        .catch((caught) => {
          if (!controller.signal.aborted) setQuestionError(errorMessage(caught));
        })
        .finally(() => {
          if (!controller.signal.aborted) setQuestionHistoryLoading(false);
        });
    }, delay);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
      questionHistoryLoadMoreControllerRef.current?.abort();
      questionHistoryLoadMoreControllerRef.current = null;
      questionHistoryLoadingMoreRef.current = false;
    };
    // The listing callback is an API adapter and does not alter the selected resource.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [planting?.id, questionSearch]);

  useEffect(() => {
    setQuestion("");
    setQuestionSearch("");
  }, [planting?.id]);

  useEffect(() => {
    setSelectedActionId(null);
    setRecordActionId(null);
    setActionQuery("");
  }, [planting?.id]);

  useEffect(() => {
    const pendingProposalIds = new Set(pendingRegenerationProposals.map((proposal) => proposal.id));
    setRegenerationDecisions((current) => Object.fromEntries(
      Object.entries(current).filter(([proposalId]) => pendingProposalIds.has(proposalId)),
    ));
    const requestedProposal = initialAiReviewRequested.current ? pendingRegenerationProposals[0] : null;
    setRegenerationReviewOpen(Boolean(requestedProposal));
    setActiveRegenerationProposalId(requestedProposal?.id ?? null);
    if (requestedProposal) {
      setWorkspace("crop");
      initialAiReviewRequested.current = false;
    }
    // The joined key changes only when the review task or its pending proposal set changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [generationTask?.id, pendingRegenerationProposalKey]);

  useEffect(() => {
    if (!generationLockActive) return;
    setAddingAction(false);
    setDraggedActionId(null);
    setDragOverColumn(null);
    setDropMessage("AI栽培計画の作成中は、圃場の作業編集を一時停止しています。");
  }, [generationLockActive]);

  const actionEntries = useMemo(() => activePlantings.flatMap((item) => (
    (bundle.calendars[item.id]?.actions ?? []).map((action) => ({ action, planting: item }))
  )), [activePlantings, bundle.calendars]);
  const actionOwnerById = useMemo(
    () => new Map(actionEntries.map((entry) => [entry.action.id, entry.planting])),
    [actionEntries],
  );
  const actionTypes = bundle.action_types?.length ? bundle.action_types : FALLBACK_ACTION_TYPES;
  const actionTypeByCode = useMemo(() => new Map(actionTypes.map((item) => [item.code, item])), [actionTypes]);
  const scopedActionEntries = useMemo(() => actionEntries.filter((entry) => (
    workScopePlantingId === "all" || entry.planting.id === workScopePlantingId
  )), [actionEntries, workScopePlantingId]);
  const scopedWorkLogs = useMemo(() => bundle.work_logs.filter((workLog) => (
    workScopePlantingId === "all" || workLog.planting_id === workScopePlantingId
  )), [bundle.work_logs, workScopePlantingId]);
  const memberTaskSummaries = useMemo(
    () => buildMemberTaskSummaries(scopedActionEntries.map((entry) => entry.action), scopedWorkLogs),
    [scopedActionEntries, scopedWorkLogs],
  );
  const visibleMemberTaskSummaries = useMemo(() => {
    if (bundle.viewer.role === "admin") return memberTaskSummaries;
    const viewerEmail = bundle.viewer.email.toLocaleLowerCase();
    return [memberTaskSummaries.find((summary) => summary.email === viewerEmail) ?? {
      email: viewerEmail,
      approvedCount: 0,
      pendingCount: 0,
      latestApprovedOn: "",
    }].filter((summary) => summary.email);
  }, [bundle.viewer.email, bundle.viewer.role, memberTaskSummaries]);
  useEffect(() => {
    if (!assignmentScope.startsWith("member:")) return;
    const selectedMemberEmail = assignmentScope.slice("member:".length);
    if (!visibleMemberTaskSummaries.some((summary) => summary.email === selectedMemberEmail)) {
      setAssignmentScope("recommended");
    }
  }, [assignmentScope, visibleMemberTaskSummaries]);
  const filteredActionEntries = useMemo(() => {
    const terms = normalizeActionSearch(actionQuery).split(/\s+/).filter(Boolean);
    return scopedActionEntries.filter(({ action, planting: owner }) => {
      const viewerEmail = bundle.viewer.email.toLocaleLowerCase();
      const assignedTo = action.assigned_to.toLocaleLowerCase();
      const performedBy = action.completion?.performed_by.toLocaleLowerCase() ?? "";
      const effectiveAssignmentScope = assignmentScope === "recommended"
        ? bundle.viewer.role === "admin" ? "all" : "available"
        : assignmentScope;
      if (effectiveAssignmentScope === "mine" && assignedTo !== viewerEmail) return false;
      if (effectiveAssignmentScope === "unassigned" && assignedTo) return false;
      if (effectiveAssignmentScope === "available" && assignedTo && assignedTo !== viewerEmail) return false;
      if (effectiveAssignmentScope.startsWith("member:")) {
        const memberEmail = effectiveAssignmentScope.slice("member:".length);
        if (assignedTo !== memberEmail && performedBy !== memberEmail) return false;
      }
      if (workDate && !(action.window_start <= workDate && action.window_end >= workDate)) return false;
      if (terms.length === 0) return true;
      const searchable = normalizeActionSearch(JSON.stringify({
        crop: owner.crop_name,
        cultivar: owner.cultivar,
        placement: owner.placement_name,
        title: action.title,
        type: action.action_type,
        reason: action.reason,
        instructions: action.instructions,
        tags: action.tags,
        assignedTo,
        performedBy,
        workPlan: action.work_plan,
      }));
      return terms.every((term) => searchable.includes(term));
    });
  }, [actionQuery, assignmentScope, bundle.viewer.email, bundle.viewer.role, scopedActionEntries, workDate]);
  const filteredActions = useMemo(() => filteredActionEntries.map((entry) => entry.action), [filteredActionEntries]);
  const questionHistoryHasMore = questionHistory.length < questionHistoryTotal;
  const suggestions = useMemo(
    () => bundle.suggestions.filter((suggestion) => suggestion.planting_id === planting?.id),
    [bundle.suggestions, planting?.id],
  );
  const fertilizerApplications = useMemo(
    () => bundle.fertilizer_applications.filter((application) => application.placement_id === planting?.placement_id),
    [bundle.fertilizer_applications, planting?.placement_id],
  );
  const suggestionByActionId = useMemo(
    () => new Map(bundle.suggestions.map((suggestion) => [suggestion.action.id, suggestion.timing_state])),
    [bundle.suggestions],
  );
  const actionsByColumn = useMemo(
    () => new Map(KANBAN_COLUMNS.map((column) => [column.id, sortKanbanActions(filteredActions, column.id, suggestionByActionId)])),
    [filteredActions, suggestionByActionId],
  );
  const selectedAction = actionEntries.find((entry) => entry.action.id === selectedActionId)?.action ?? null;
  const selectedActionPlanting = selectedAction ? actionOwnerById.get(selectedAction.id) ?? null : null;

  const openActionFromGantt = (action: PlantCalendarAction) => {
    setRecordActionId(null);
    setSelectedActionId(action.id);
  };

  const closeAction = () => {
    setSelectedActionId(null);
    setRecordActionId(null);
  };

  useEffect(() => {
    if (
      initialActionId
      && initialActionId !== consumedInitialActionId.current
      && actionEntries.some((entry) => entry.action.id === initialActionId)
    ) {
      consumedInitialActionId.current = initialActionId;
      setSelectedActionId(initialActionId);
    }
  }, [actionEntries, initialActionId]);

  const moveAction = async (destination: KanbanColumn) => {
    const action = filteredActions.find((item) => item.id === draggedActionId)
      ?? actionEntries.find((entry) => entry.action.id === draggedActionId)?.action;
    setDragOverColumn(null);
    setDraggedActionId(null);
    const owner = action ? actionOwnerById.get(action.id) : null;
    if (!action || !owner || calendarMutationBusy || !canDropAction(action, destination)) return;
    try {
      if (destination === "awaiting_review") {
        if (action.status === "planned") {
          await onEditAction(owner.id, action.id, { status: "in_progress", use_as_guidance: false });
        }
        setSelectedActionId(action.id);
        setRecordActionId(action.id);
        setDropMessage(`${action.title}の実績入力を開きました。保存すると管理者の確認待ちになります。`);
        return;
      }
      const status = destination === "planned" ? "planned" : "in_progress";
      await onEditAction(owner.id, action.id, { status, use_as_guidance: false });
      setDropMessage(`${action.title}を${destination === "planned" ? "未完了" : "作業中"}へ移動しました。`);
    } catch (caught) {
      setDropMessage(errorMessage(caught));
    }
  };

  const regenerate = async (event: FormEvent) => {
    event.preventDefault();
    if (!planting) return;
    setGenerationError("");
    setActiveOperation("regenerate");
    try {
      await onRegenerate(planting.id, generationStart, generationNotes, calendar ? generationMode : "automatic");
      setGenerationOpen(false);
    } catch (caught) {
      setGenerationError(errorMessage(caught));
    } finally {
      setActiveOperation(null);
    }
  };

  const openRegenerationReview = (proposalId?: string) => {
    setGenerationError("");
    const nextProposal = pendingRegenerationProposals.find((proposal) => !regenerationDecisions[proposal.id]);
    setActiveRegenerationProposalId(proposalId ?? nextProposal?.id ?? null);
    setRegenerationReviewOpen(true);
  };

  const decideRegenerationProposalAndContinue = (proposalId: string, decision: RegenerationDecision) => {
    setGenerationError("");
    const nextDecisions = { ...regenerationDecisions, [proposalId]: decision };
    setRegenerationDecisions(nextDecisions);
    const currentIndex = pendingRegenerationProposals.findIndex((proposal) => proposal.id === proposalId);
    const followingProposals = [
      ...pendingRegenerationProposals.slice(currentIndex + 1),
      ...pendingRegenerationProposals.slice(0, Math.max(currentIndex, 0)),
    ];
    const nextProposal = followingProposals.find((proposal) => !nextDecisions[proposal.id]);
    setActiveRegenerationProposalId(nextProposal?.id ?? null);
  };

  const applyRegenerationDecisions = async () => {
    if (!planting || !generationTask) return;
    if (!pendingRegenerationProposals.length || undecidedRegenerationCount > 0) return;
    setGenerationError("");
    setActiveOperation("review-decisions");
    try {
      await onDecideRegeneration(
        planting.id,
        generationTask.id,
        pendingRegenerationProposals.map((proposal) => ({
          proposal_id: proposal.id,
          decision: regenerationDecisions[proposal.id]!,
        })),
      );
      setRegenerationDecisions({});
      setRegenerationReviewOpen(false);
      setActiveRegenerationProposalId(null);
    } catch (caught) {
      setGenerationError(errorMessage(caught));
    } finally {
      setActiveOperation(null);
    }
  };

  const loadOlderQuestions = async () => {
    if (
      !planting
      || questionHistoryLoading
      || questionHistoryLoadingMoreRef.current
      || !questionHistoryHasMore
      || questionHistoryQueryRef.current !== questionSearch.trim()
    ) return;
    questionHistoryPointerScrollRef.current = false;
    questionHistoryTouchYRef.current = null;
    const history = chatHistoryRef.current;
    const previousHeight = history?.scrollHeight ?? 0;
    const previousTop = history?.scrollTop ?? 0;
    const nextPage = questionHistoryPage + 1;
    const controller = new AbortController();
    questionHistoryLoadMoreControllerRef.current = controller;
    questionHistoryLoadingMoreRef.current = true;
    setQuestionHistoryLoadingMore(true);
    setQuestionError("");
    try {
      const result = await onListQuestions(planting.id, {
        query: questionSearch.trim(),
        page: nextPage,
        pageSize: QUESTION_HISTORY_PAGE_SIZE,
        signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      setQuestionHistory((current) => {
        const existingIds = new Set(current.map((item) => item.id));
        return [...current, ...result.items.filter((item) => !existingIds.has(item.id))];
      });
      setQuestionHistoryPage(nextPage);
      setQuestionHistoryTotal(result.total);
      window.requestAnimationFrame(() => window.requestAnimationFrame(() => {
        const currentHistory = chatHistoryRef.current;
        if (currentHistory) currentHistory.scrollTop = previousTop + currentHistory.scrollHeight - previousHeight;
      }));
    } catch (caught) {
      if (!controller.signal.aborted) setQuestionError(errorMessage(caught));
    } finally {
      if (questionHistoryLoadMoreControllerRef.current === controller) {
        questionHistoryLoadMoreControllerRef.current = null;
        questionHistoryLoadingMoreRef.current = false;
        setQuestionHistoryLoadingMore(false);
      }
    }
  };

  const ask = async (event: FormEvent) => {
    event.preventDefault();
    if (!planting || !question.trim()) return;
    setQuestionError("");
    setActiveOperation("question");
    try {
      const record = await onAskQuestion(planting.id, question.trim());
      setQuestionHistory((current) => [record, ...current.filter((item) => item.id !== record.id)]);
      setQuestionHistoryTotal((current) => current + 1);
      setQuestion("");
      setQuestionSearch("");
      window.requestAnimationFrame(() => {
        const history = chatHistoryRef.current;
        if (history) history.scrollTo({ top: history.scrollHeight, behavior: "smooth" });
      });
    } catch (caught) {
      setQuestionError(errorMessage(caught));
    } finally {
      setActiveOperation(null);
    }
  };

  const openGenerationFromKanban = () => {
    const lockedPlantingId = generationLockTasks[0]?.planting_id;
    if (lockedPlantingId && lockedPlantingId !== planting?.id) onPlantingChange(lockedPlantingId);
    setWorkspace("crop");
    window.setTimeout(() => document.getElementById("calendar-generation-section")?.scrollIntoView({ behavior: "smooth", block: "start" }), 80);
  };

  const panel = (
      <aside className={`calendar-drawer ${presentation === "page" ? "calendar-page-panel" : "calendar-modal-panel"}${generationLockActive ? " calendar-edit-locked" : ""}`} data-calendar-edit-locked={generationLockActive ? "true" : "false"} role={presentation === "modal" ? "dialog" : undefined} aria-modal={presentation === "modal" ? "true" : undefined} aria-label="栽培カレンダー">
        <header className="calendar-header">
          <div className="calendar-header-identity">
            {presentation === "page" && <a className="icon-link labeled-icon-button" href={fieldDetailUrl} aria-label={`${fieldName || "圃場"}へ戻る`} title={`${fieldName || "圃場"}へ戻る`}><ArrowLeft size={19} /><span>圃場へ戻る</span></a>}
            <div><span>{fieldName || "栽培支援"}</span>{presentation === "page" ? <h1>年間栽培カレンダー</h1> : <h2>生成した栽培カレンダー</h2>}</div>
          </div>
          {presentation === "modal" && <button type="button" className="icon-button labeled-icon-button" onClick={onClose} aria-label="栽培カレンダーを閉じる" title="閉じる"><X size={19} /><span>閉じる</span></button>}
        </header>

        {(busy || activeOperation) && <div className="calendar-operation-indicator"><InlineLoading label={operationMessage} /></div>}

        {activePlantings.length === 0 ? (
          <CalendarEmptyState />
        ) : planting && (
          <>
            <nav className="calendar-workspace-tabs" aria-label="年間栽培カレンダーの表示">
              <button type="button" className={workspace === "work" ? "active" : ""} aria-pressed={workspace === "work"} onClick={() => setWorkspace("work")}><ListTodo size={17} /><span>圃場の作業</span><small>全作物をまとめて確認</small></button>
              <button type="button" className={workspace === "crop" ? "active" : ""} aria-pressed={workspace === "crop"} onClick={() => setWorkspace("crop")}><Leaf size={17} /><span>作物別の栽培計画</span><small>栽培基準・施肥・AI計画</small></button>
            </nav>
            {generationLockActive && (
              <div className="calendar-edit-lock" role="status" aria-live="polite">
                <span className="calendar-edit-lock-icon"><LockKeyhole size={21} /></span>
                <div><strong>AI栽培計画を作成中のため、作業編集を一時停止しています</strong><p>閲覧・検索・日付フィルタは利用できます。完了後に自動で編集できるようになります。</p></div>
                <span className="calendar-edit-lock-count">{generationLockTasks.length}件を処理中</span>
              </div>
            )}

            <div className="calendar-workspace-layout">
            <main className="calendar-workspace-main">
            {workspace === "crop" && <>
            <section className="calendar-plant-selector">
              <div className="filterable-field">
                <span className="field-label">管理する作物</span>
                <SearchableSelect
                  ariaLabel="管理する作物"
                  value={planting.id}
                  onChange={onPlantingChange}
                  searchPlaceholder="作物、品種、設置場所を検索"
                  emptyMessage="一致する栽培はありません。"
                  options={activePlantings.map((item) => ({
                    value: item.id,
                    label: `${item.placement_name} / ${item.crop_name}${item.cultivar ? ` (${item.cultivar})` : ""}`,
                    searchText: `${item.crop_name} ${item.cultivar} ${item.placement_name}`,
                  }))}
                />
              </div>
              <div className="plant-context">
                <span><Leaf size={15} />{planting.crop_name}</span>
                <span>{planting.placement_name}</span>
                <span>{formatDate(planting.planted_on)} 定植</span>
              </div>
            </section>

            {calendar && <CareProfileSummary calendar={calendar} />}
            <SuggestionSummary suggestions={suggestions} />

            <section className="calendar-generation" id="calendar-generation-section" aria-label="計画の生成設定">
              <div className="calendar-section-heading">
                <div><Sparkles size={17} /><strong>AI栽培計画を作り直す</strong></div>
                <button type="button" disabled={generationActive || generationReviewPending} aria-busy={generationActive} onClick={() => setGenerationOpen(true)}>
                  {!generationActive && <RefreshCw size={15} />}
                  {generationActive ? "AI計画を作成中..." : generationReviewPending ? "変更案を確認中" : calendar ? "作り直す条件を確認" : "作成条件を確認"}
                </button>
              </div>
              {!generationOpen && !generationActive && <p className="calendar-regeneration-intro">施肥履歴や現在の栽培条件を反映して、これからの予定を作り直す場合に使います。普段の作業追加には使用しません。</p>}
              {generationActive && (
                <div className="generation-status active" role="status" aria-live="polite">
                  <ActivityIndicator size="small" />
                  <div><strong>{generationTask.status === "queued" ? "AI計画の作成を待っています" : "AI計画を作成しています"}</strong><p>この画面を離れても処理は続きます。閲覧や検索はできますが、計画の整合性を守るため作業編集は完了まで停止します。</p></div>
                </div>
              )}
              {generationTask?.status === "failed" && (
                <div className="generation-status failed" role="alert">
                  <div><strong>AI計画を作成できませんでした</strong><p>{generationTask.error || "時間をおいてもう一度お試しください。"}</p></div>
                </div>
              )}
              {generationReviewPending && generationTask && (
                <div className="calendar-regeneration-review" role="region" aria-label="AI計画の変更案">
                  <button type="button" className="regeneration-review-entry" onClick={() => openRegenerationReview()}>
                    <span className="regeneration-review-entry-icon"><Sparkles size={21} /></span>
                    <span className="regeneration-review-entry-copy">
                      <strong>AIから{pendingRegenerationProposals.length}件の変更案があります</strong>
                      <small>カードを開いて現在の作業と比較し、1件ずつ判断します。選択中は通信しません。</small>
                    </span>
                    <span className="regeneration-review-entry-action">
                      {undecidedRegenerationCount === pendingRegenerationProposals.length ? "確認を始める" : undecidedRegenerationCount > 0 ? "確認を続ける" : "確認結果を見る"}
                      <ChevronRight size={17} />
                    </span>
                  </button>
                  <div className="regeneration-review-counts" aria-live="polite">
                    <span className="approved"><Check size={14} />取り入れる {approvedRegenerationCount}件</span>
                    <span className="rejected"><X size={14} />取り入れない {rejectedRegenerationCount}件</span>
                    <span className={undecidedRegenerationCount ? "pending" : "complete"}>未確認 {undecidedRegenerationCount}件</span>
                  </div>
                  <div className="regeneration-proposal-queue" aria-label="変更案の確認状況">
                    {pendingRegenerationProposals.map((proposal, index) => {
                      const previewAction = proposal.after ?? proposal.before;
                      const stagedDecision = regenerationDecisions[proposal.id];
                      return (
                        <button
                          key={proposal.id}
                          type="button"
                          className={`regeneration-proposal-card ${proposal.change_type}${stagedDecision ? ` ${stagedDecision}` : ""}`}
                          onClick={() => openRegenerationReview(proposal.id)}
                          aria-label={`${index + 1}件目「${proposal.title}」を比較する`}
                        >
                          <span className="regeneration-proposal-number">{index + 1}</span>
                          <span className="regeneration-proposal-card-copy">
                            <small>{regenerationChangeLabel(proposal.change_type)}</small>
                            <strong>{proposal.title}</strong>
                            {previewAction && <span>{formatDate(previewAction.window_start)}〜{formatDate(previewAction.window_end)}</span>}
                          </span>
                          <span className={`regeneration-proposal-decision ${stagedDecision ?? "pending"}`}>
                            {stagedDecision === "approved" ? "取り入れる" : stagedDecision === "rejected" ? "取り入れない" : "未確認"}
                          </span>
                          <ChevronRight size={17} aria-hidden="true" />
                        </button>
                      );
                    })}
                  </div>
                  {generationError && <p className="form-error">{generationError}</p>}
                  <div className="regeneration-commit-bar">
                    <div>
                      <strong>{undecidedRegenerationCount > 0 ? `あと${undecidedRegenerationCount}件を確認してください` : `${pendingRegenerationProposals.length}件の確認が完了しました`}</strong>
                      <span>{generationError ? "選択内容は残っています。比較画面からもう一度反映できます。" : "判断すると自動で次の変更案へ進みます。"}</span>
                    </div>
                    <button type="button" className="primary" disabled={!pendingRegenerationProposals.length} onClick={() => openRegenerationReview()}>
                      {undecidedRegenerationCount > 0 ? <ChevronRight size={15} /> : <Check size={15} />}
                      {undecidedRegenerationCount > 0 ? "1件ずつ比較する" : "確認結果を反映する"}
                    </button>
                  </div>
                </div>
              )}
            </section>
            {generationOpen && (
              <ModalDialog
                title={calendar ? "AI栽培計画を作り直す" : "AI栽培計画を作成する"}
                eyebrow="現在の記録を守りながら、これからの計画を更新"
                onClose={() => setGenerationOpen(false)}
                className="calendar-generation-dialog"
                size="wide"
              >
                <form className="calendar-generation-form" onSubmit={(event) => void regenerate(event)}>
                  <label>計画開始日<input type="date" required value={generationStart} onChange={(event) => setGenerationStart(event.target.value)} /></label>
                  <label>今回の生成条件<textarea value={generationNotes} onChange={(event) => setGenerationNotes(event.target.value)} placeholder="今年は収穫を優先、農薬を使わない、現在は開花直前など" /></label>
                  {calendar && <fieldset className="generation-mode-fieldset"><legend>変更の反映方法</legend><div className="generation-mode-options">
                    <label className={generationMode === "review" ? "selected" : ""}><input type="radio" name="generation_mode" value="review" checked={generationMode === "review"} onChange={() => setGenerationMode("review")} /><strong>確認しながら変更</strong><span>おすすめ。変更・追加・削除を今の予定と比較して選び、最後にまとめて反映します。</span></label>
                    <label className={generationMode === "automatic" ? "selected" : ""}><input type="radio" name="generation_mode" value="automatic" checked={generationMode === "automatic"} onChange={() => setGenerationMode("automatic")} /><strong>全自動で立て直す</strong><span>現在の計画をAIが整理し、妥当な作業を残しながら必要な差分を自動反映します。</span></label>
                  </div></fieldset>}
                  <p>現在の{calendar?.actions.length ?? 0}件の作業、実績、施肥履歴、栽培条件をAIへ渡します。実施済み・作業中の記録は削除せず、同じ目的の作業は重複させません。</p>
                  <DisabledActionReason id="calendar-regeneration-blocked" reasons={regenerationBlockingReasons} prefix="再生成するには" />
                  {generationError && <p className="form-error">{generationError}</p>}
                  <div className="form-actions">
                    <button type="button" onClick={() => setGenerationOpen(false)}>キャンセル</button>
                    <button type="submit" disabled={regenerationBlockingReasons.length > 0 || activeOperation === "regenerate"} aria-busy={activeOperation === "regenerate"} aria-describedby={regenerationBlockingReasons.length > 0 ? "calendar-regeneration-blocked" : undefined} title={disabledActionTitle(regenerationBlockingReasons)}>{activeOperation !== "regenerate" && <Sparkles size={15} />}{activeOperation === "regenerate" ? "変更案を作成しています" : calendar && generationMode === "review" ? "変更案を作成" : `これからの12か月計画を${calendar ? "作り直す" : "作成"}`}</button>
                  </div>
                </form>
              </ModalDialog>
            )}
            <FertilizerEffectPanel
              plantingId={planting.id}
              placementName={planting.placement_name}
              applications={fertilizerApplications}
              materials={bundle.fertilizer_materials}
              busy={calendarMutationBusy}
              locked={generationLockActive}
              onAdd={onAddFertilizer}
              onDelete={onDeleteFertilizer}
              onSaveMaterial={onSaveFertilizerMaterial}
              onDeleteMaterial={onDeleteFertilizerMaterial}
            />
            </>}

            {workspace === "work" && <>
              <SuggestionSummary suggestions={bundle.suggestions} />
              {actionEntries.length > 0 && <div className="calendar-outlook"><AnnualCalendarGantt actions={scopedActionEntries.map((entry) => entry.action)} onActionSelect={openActionFromGantt} /></div>}
            </>}

            {workspace === "work" && <section className="calendar-action-list" aria-label="管理作業">
              <div className="calendar-section-heading">
                <div><strong>圃場の管理作業</strong><span>{scopedActionEntries.length}件を状態別に管理</span></div>
                <div>
                  {!addingAction && <button type="button" onClick={() => { setNewActionPlantingId(workScopePlantingId === "all" ? planting.id : workScopePlantingId); setAddingAction(true); }} disabled={calendarMutationBusy} title={calendarMutationBusy ? "AI計画の作成または現在の操作が完了するまでお待ちください" : "管理作業を追加"}><Plus size={15} />作業を追加</button>}
                </div>
              </div>
              <MemberTaskCompletionSummary
                summaries={visibleMemberTaskSummaries}
                selectedScope={assignmentScope}
                teamView={bundle.viewer.role === "admin"}
                onSelect={(email) => setAssignmentScope((current) => current === memberAssignmentScope(email) ? "recommended" : memberAssignmentScope(email))}
              />
              <div className="calendar-kanban-toolbar">
                <label className="calendar-action-date"><CalendarDays size={16} /><span>この日に行う作業</span><input type="date" value={workDate} onChange={(event) => setWorkDate(event.target.value)} aria-label="作業期間に含まれる日" />{workDate && <button type="button" onClick={() => setWorkDate("")} aria-label="日付フィルタを解除" title="日付フィルタを解除"><X size={14} /></button>}</label>
                <label className="calendar-action-search"><Search size={16} /><input type="search" value={actionQuery} onChange={(event) => setActionQuery(event.target.value)} placeholder="作物、場所、作業名、資材をあいまい検索" aria-label="管理作業を検索" />{actionQuery && <button type="button" onClick={() => setActionQuery("")} aria-label="作業検索をクリア" title="作業検索をクリア"><X size={14} /></button>}</label>
                <div className="calendar-work-scope filterable-field">
                  <span className="field-label">表示する作物</span>
                  <SearchableSelect
                    ariaLabel="表示する作物"
                    value={workScopePlantingId}
                    onChange={setWorkScopePlantingId}
                    searchPlaceholder="作物、品種、設置場所を検索"
                    emptyMessage="一致する栽培はありません。"
                    options={[
                      { value: "all", label: `圃場のすべての作物（${actionEntries.length}件）`, fixed: true },
                      ...activePlantings.map((item) => ({ value: item.id, label: `${item.placement_name} / ${item.crop_name}${item.cultivar ? ` (${item.cultivar})` : ""}`, searchText: `${item.crop_name} ${item.cultivar} ${item.placement_name}` })),
                    ]}
                  />
                </div>
                <div className="calendar-work-scope calendar-assignment-scope filterable-field">
                  <span className="field-label">担当者</span>
                  <SearchableSelect
                    ariaLabel="担当者で絞り込む"
                    value={assignmentScope}
                    onChange={(value) => setAssignmentScope(value as AssignmentScope)}
                    searchPlaceholder="担当範囲を検索"
                    emptyMessage="一致する担当範囲はありません。"
                    options={[
                      { value: "recommended", label: bundle.viewer.role === "admin" ? "すべての担当者（おすすめ）" : "自分が担当できる作業（おすすめ）", fixed: true },
                      { value: "mine", label: `自分の担当（${bundle.viewer.email || "ログイン中"}）`, fixed: true },
                      { value: "unassigned", label: "担当者未設定", fixed: true },
                      { value: "all", label: "すべての担当者", fixed: true },
                      ...visibleMemberTaskSummaries.map((summary) => ({
                        value: memberAssignmentScope(summary.email),
                        label: `${summary.email}（完遂 ${summary.approvedCount}件）`,
                        searchText: summary.email,
                      })),
                    ]}
                  />
                </div>
                <output>{filteredActions.length} / {scopedActionEntries.length}件</output>
              </div>
              <div className="calendar-kanban-guidance">
                {(actionQuery || workDate || workScopePlantingId !== "all" || assignmentScope !== "recommended") && <span className="calendar-filter-active">絞り込み中</span>}
                <HelpDisclosure title="作業ボードの使い方" align="left">
                  <p>検索や日付を指定すると、条件に合う作業だけを表示します。日付では、その日が作業期間に含まれる作業を探します。</p>
                  <p>{generationLockActive ? "AI計画の作成中は閲覧のみです。完了するとカードの移動と編集が自動で再開します。" : "カードを列へドラッグすると状態を変更できます。確認待ちへ移すと実績入力が開きます。"}</p>
                </HelpDisclosure>
              </div>
              <p className="kanban-drop-status" role="status" aria-live="polite">{dropMessage}</p>
              <div className="calendar-kanban-stage">
              <div className="calendar-kanban-scroll">
                <div className="calendar-kanban" aria-label="管理作業カンバン">
                  {KANBAN_COLUMNS.map((column) => {
                    const columnActions = actionsByColumn.get(column.id) ?? [];
                    return (
                      <section
                        key={column.id}
                        className={`calendar-kanban-column ${column.id}${dragOverColumn === column.id ? " drag-over" : ""}`}
                        data-kanban-status={column.id}
                        aria-labelledby={`kanban-column-${planting.id}-${column.id}`}
                        onDragOver={(event) => {
                          const action = filteredActions.find((item) => item.id === draggedActionId)
                            ?? actionEntries.find((entry) => entry.action.id === draggedActionId)?.action;
                          if (!action || calendarMutationBusy || !canDropAction(action, column.id)) return;
                          event.preventDefault();
                          event.dataTransfer.dropEffect = "move";
                          setDragOverColumn(column.id);
                        }}
                        onDragLeave={(event) => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragOverColumn(null); }}
                        onDrop={(event) => { event.preventDefault(); void moveAction(column.id); }}
                      >
                        <header>
                          <div><span className="kanban-column-marker" /><h3 id={`kanban-column-${planting.id}-${column.id}`}>{column.label}</h3><strong>{columnActions.length}</strong></div>
                          <HelpDisclosure title={`${column.label}とは`}><p>{column.description}</p></HelpDisclosure>
                          <small>{formatPersonHours(columnActions)}人時</small>
                        </header>
                        <div className="calendar-kanban-cards">
                          {columnActions.map((action) => (
                            <CalendarKanbanCard
                              key={action.id}
                              action={action}
                              actionType={actionTypeByCode.get(action.action_type) ?? actionTypeByCode.get("other") ?? FALLBACK_ACTION_TYPES[FALLBACK_ACTION_TYPES.length - 1]}
                              timingState={suggestionByActionId.get(action.id)}
                              cropLabel={`${actionOwnerById.get(action.id)?.crop_name ?? "作物"} / ${actionOwnerById.get(action.id)?.placement_name ?? "未設定"}`}
                              onOpen={() => { setRecordActionId(null); setSelectedActionId(action.id); }}
                              draggable={
                                !calendarMutationBusy
                                && ["planned", "in_progress", "skipped"].includes(action.status)
                                && (bundle.viewer.role === "admin" || !action.assigned_to || action.assigned_to.toLocaleLowerCase() === bundle.viewer.email.toLocaleLowerCase())
                              }
                              onDragStart={(event) => {
                                setDraggedActionId(action.id);
                                setDropMessage("");
                                event.dataTransfer.effectAllowed = "move";
                                event.dataTransfer.setData("text/plain", action.id);
                              }}
                              onDragEnd={() => { setDraggedActionId(null); setDragOverColumn(null); }}
                            />
                          ))}
                          {columnActions.length === 0 && <KanbanEmptyState column={column.id} />}
                        </div>
                      </section>
                    );
                  })}
                </div>
              </div>
              {generationLockActive && (
                <div className="calendar-kanban-lock-overlay" role="status" aria-live="polite">
                  <span><LockKeyhole size={26} /></span>
                  <strong>AIが栽培計画を整理しています</strong>
                  <p>作業の重複や消失を防ぐため、完了までカンバンの編集を停止しています。</p>
                  <button type="button" aria-busy="true" onClick={openGenerationFromKanban}>AI栽培計画を完了してください</button>
                </div>
              )}
              </div>
            </section>}

            </main>

            <aside className="plant-question" aria-label={`${planting.crop_name}の栽培相談`}>
              <header>
                <div><span className="plant-chat-avatar"><Sprout size={20} /></span><div><strong>この作物について質問</strong><small>{planting.crop_name}の計画と記録を参照</small></div></div>
                <span className="plant-chat-scope">栽培専用</span>
              </header>
              <label className="plant-chat-search"><Search size={15} /><input type="search" value={questionSearch} onChange={(event) => setQuestionSearch(event.target.value)} placeholder="過去の質問と回答を検索" aria-label="過去の栽培相談を検索" />{questionSearch && <button type="button" onClick={() => setQuestionSearch("")} aria-label="相談履歴の検索をクリア"><X size={14} /></button>}</label>
              <div
                className="plant-chat-history"
                ref={chatHistoryRef}
                aria-live="polite"
                aria-busy={questionHistoryLoading || questionHistoryLoadingMore}
                data-question-page={questionHistoryPage}
                onScroll={(event) => {
                  if (questionHistoryPointerScrollRef.current && event.currentTarget.scrollTop <= 32) {
                    questionHistoryPointerScrollRef.current = false;
                    void loadOlderQuestions();
                  }
                }}
                onWheel={(event) => {
                  if (event.deltaY < 0 && event.currentTarget.scrollTop <= 32) void loadOlderQuestions();
                }}
                onTouchStart={(event) => { questionHistoryTouchYRef.current = event.touches[0]?.clientY ?? null; }}
                onTouchMove={(event) => {
                  const currentY = event.touches[0]?.clientY ?? null;
                  if (currentY !== null && questionHistoryTouchYRef.current !== null && currentY > questionHistoryTouchYRef.current && event.currentTarget.scrollTop <= 32) {
                    void loadOlderQuestions();
                  }
                  questionHistoryTouchYRef.current = currentY;
                }}
                onTouchEnd={() => { questionHistoryTouchYRef.current = null; }}
                onPointerDown={(event) => { questionHistoryPointerScrollRef.current = event.pointerType === "mouse"; }}
                onPointerUp={() => { questionHistoryPointerScrollRef.current = false; }}
                onPointerCancel={() => { questionHistoryPointerScrollRef.current = false; }}
                onKeyDown={(event) => {
                  if (["ArrowUp", "PageUp", "Home"].includes(event.key) && event.currentTarget.scrollTop <= 32) void loadOlderQuestions();
                }}
              >
                {questionHistoryLoading && <InlineLoading label="相談履歴を読み込んでいます" />}
                {!questionHistoryLoading && questionHistoryLoadingMore && <div className="plant-chat-history-progress"><InlineLoading label="過去の相談を読み込んでいます" /></div>}
                {!questionHistoryLoading && questionHistoryHasMore && !questionHistoryLoadingMore && questionHistory.length > 0 && (
                  <button className="plant-chat-load-older" type="button" onClick={() => void loadOlderQuestions()}>上へスクロールすると過去の相談を読み込みます</button>
                )}
                {!questionHistoryLoading && questionHistory.length === 0 && (
                  <div className="plant-chat-empty"><MessageCircle size={27} /><strong>{questionSearch ? "一致する相談はありません" : "栽培の疑問をすぐ相談できます"}</strong><p>{questionSearch ? "別の言葉で検索してください。" : "計画、作業、施肥、病害虫など、この作物に関する質問を入力してください。"}</p></div>
                )}
                {[...questionHistory].reverse().map((record) => (
                  <article className="plant-chat-turn" key={record.id}>
                    <div className="plant-chat-message user"><span>あなた</span><p>{record.question}</p><time dateTime={record.created_at}>{formatChatTime(record.created_at)}</time></div>
                    <div className="plant-chat-message assistant"><span>栽培アシスタント</span><p>{record.answer}</p></div>
                  </article>
                ))}
              </div>
              <form className="plant-chat-compose" onSubmit={(event) => void ask(event)}>
                <label htmlFor="plant-chat-question">栽培について質問する</label>
                <textarea id="plant-chat-question" value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="例：追肥は今必要ですか？" rows={3} />
                <button type="submit" disabled={questionBlockingReasons.length > 0 || activeOperation === "question"} aria-busy={activeOperation === "question"} aria-describedby={questionBlockingReasons.length > 0 ? "plant-question-blocked" : undefined} title={disabledActionTitle(questionBlockingReasons)}>{activeOperation !== "question" && <Send size={16} />}{activeOperation === "question" ? "回答を考えています" : "質問を送る"}</button>
              </form>
              <DisabledActionReason id="plant-question-blocked" reasons={questionBlockingReasons} prefix="質問するには" />
              {questionError && <p className="form-error" role="alert">{questionError}</p>}
              <p className="safety-note">登録作物と農作業以外の質問は回答・保存しません。農薬は対象作物の登録、ラベル、地域指針を必ず確認してください。</p>
            </aside>
            </div>

            {regenerationReviewOpen && generationTask && (
              <div className="calendar-action-detail-backdrop regeneration-review-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setRegenerationReviewOpen(false); }}>
                <section className="calendar-action-detail-dialog regeneration-review-dialog" role="dialog" aria-modal="true" aria-labelledby="regeneration-review-dialog-title">
                  <header>
                    <div>
                      <span>{activeRegenerationProposal ? `AI変更案 ${activeRegenerationProposalIndex + 1} / ${pendingRegenerationProposals.length}` : "AI変更案の確認結果"}</span>
                      <h2 id="regeneration-review-dialog-title">{activeRegenerationProposal?.title ?? `${pendingRegenerationProposals.length}件の確認が完了しました`}</h2>
                    </div>
                    <button type="button" className="icon-button labeled-icon-button" onClick={() => setRegenerationReviewOpen(false)} aria-label="変更案一覧へ戻る" title="変更案一覧へ戻る"><X size={19} /><span>一覧へ戻る</span></button>
                  </header>
                  <div className="calendar-action-detail-body regeneration-review-dialog-body">
                    {activeRegenerationProposal ? (
                      <>
                        <div className="regeneration-review-progress" aria-label={`${activeRegenerationProposalIndex + 1}件目 / 全${pendingRegenerationProposals.length}件`}>
                          <span style={{ width: `${((activeRegenerationProposalIndex + 1) / pendingRegenerationProposals.length) * 100}%` }} />
                        </div>
                        <div className="regeneration-review-guidance">
                          <span>{regenerationChangeLabel(activeRegenerationProposal.change_type)}</span>
                          <p>現在の計画とAIの案を見比べて、この変更を取り入れるか判断してください。判断すると次の未確認案へ進みます。</p>
                        </div>
                        <div className={`regeneration-action-comparison ${activeRegenerationProposal.change_type}`}>
                          <section className="regeneration-comparison-side current" aria-label="現在の栽培カレンダー">
                            <header><span>現在</span><strong>現在の栽培カレンダー</strong></header>
                            {activeRegenerationProposal.before ? (
                              <CalendarActionPreview
                                action={activeRegenerationProposal.before}
                                actionType={actionTypeByCode.get(activeRegenerationProposal.before.action_type) ?? actionTypeByCode.get("other") ?? FALLBACK_ACTION_TYPES[FALLBACK_ACTION_TYPES.length - 1]}
                              />
                            ) : (
                              <div className="regeneration-comparison-empty"><PackageOpen size={29} /><strong>現在はこの作業がありません</strong><p>AIが新しく追加を提案しています。</p></div>
                            )}
                          </section>
                          <section className="regeneration-comparison-side proposed" aria-label="AIの提案">
                            <header><span>変更後</span><strong>AIの提案</strong></header>
                            {activeRegenerationProposal.after ? (
                              <CalendarActionPreview
                                action={activeRegenerationProposal.after}
                                actionType={actionTypeByCode.get(activeRegenerationProposal.after.action_type) ?? actionTypeByCode.get("other") ?? FALLBACK_ACTION_TYPES[FALLBACK_ACTION_TYPES.length - 1]}
                              />
                            ) : (
                              <div className="regeneration-comparison-empty delete"><Trash2 size={29} /><strong>この作業を削除する提案です</strong><p>取り入れると現在の栽培カレンダーから削除されます。</p></div>
                            )}
                          </section>
                        </div>
                        <div className="regeneration-review-decision-bar">
                          <div>
                            <small>この変更案をどうしますか？</small>
                            {regenerationDecisions[activeRegenerationProposal.id] && <span>前回の選択: {regenerationDecisions[activeRegenerationProposal.id] === "approved" ? "取り入れる" : "取り入れない"}</span>}
                          </div>
                          <div>
                            <button
                              type="button"
                              className="reject"
                              aria-pressed={regenerationDecisions[activeRegenerationProposal.id] === "rejected"}
                              disabled={busy}
                              onClick={() => decideRegenerationProposalAndContinue(activeRegenerationProposal.id, "rejected")}
                            ><X size={17} />取り入れない</button>
                            <button
                              type="button"
                              className="approve"
                              aria-pressed={regenerationDecisions[activeRegenerationProposal.id] === "approved"}
                              disabled={busy}
                              onClick={() => decideRegenerationProposalAndContinue(activeRegenerationProposal.id, "approved")}
                            ><Check size={17} />{regenerationApproveLabel(activeRegenerationProposal.change_type)}</button>
                          </div>
                        </div>
                      </>
                    ) : (
                      <div className="regeneration-review-complete">
                        <span className="regeneration-review-complete-icon"><Check size={30} /></span>
                        <div><small>すべての変更案を確認しました</small><h3>{pendingRegenerationProposals.length}件の判断を栽培カレンダーへ反映します</h3><p>ここで初めてAPI通信を1回行い、選んだ内容をまとめて安全に反映します。</p></div>
                        <div className="regeneration-review-counts">
                          <span className="approved"><Check size={14} />取り入れる {approvedRegenerationCount}件</span>
                          <span className="rejected"><X size={14} />取り入れない {rejectedRegenerationCount}件</span>
                        </div>
                        {generationError && <p className="form-error">{generationError}<small>選択内容は保持されています。そのまま再試行できます。</small></p>}
                        <div className="regeneration-review-complete-actions">
                          <button type="button" onClick={() => setRegenerationReviewOpen(false)} disabled={busy}>変更案一覧へ戻る</button>
                          <button type="button" className="primary" onClick={() => void applyRegenerationDecisions()} disabled={busy || activeOperation === "review-decisions" || undecidedRegenerationCount > 0} aria-busy={activeOperation === "review-decisions"}>
                            {activeOperation !== "review-decisions" && <Check size={17} />}
                            {activeOperation === "review-decisions" ? "まとめて反映中..." : "選択した内容を一括反映"}
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                </section>
              </div>
            )}

            {addingAction && (
              <div className="calendar-action-detail-backdrop calendar-action-create-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setAddingAction(false); }}>
                <section className="calendar-action-detail-dialog calendar-action-create-dialog" role="dialog" aria-modal="true" aria-labelledby="new-calendar-action-title">
                  <header><div><span>圃場の予定へ追加</span><h2 id="new-calendar-action-title">作業を追加</h2></div><button type="button" className="icon-button labeled-icon-button" onClick={() => setAddingAction(false)} aria-label="作業追加を閉じる" title="閉じる"><X size={19} /><span>閉じる</span></button></header>
                  <div className="calendar-action-detail-body">
                    <div className="new-action-crop-selector filterable-field">
                      <span className="field-label">対象の作物</span>
                      <SearchableSelect ariaLabel="作業を追加する作物" value={newActionPlantingId} onChange={setNewActionPlantingId} searchPlaceholder="作物、品種、設置場所を検索" emptyMessage="一致する栽培はありません。" options={activePlantings.map((item) => ({ value: item.id, label: `${item.placement_name} / ${item.crop_name}${item.cultivar ? ` (${item.cultivar})` : ""}`, searchText: `${item.crop_name} ${item.cultivar} ${item.placement_name}` }))} />
                    </div>
                    <NewCalendarActionForm actionTypes={actionTypes} busy={calendarMutationBusy} canAssign={bundle.viewer.role === "admin"} onCancel={() => setAddingAction(false)} onSave={async (payload) => { await onAddAction(newActionPlantingId, payload); setAddingAction(false); }} />
                  </div>
                </section>
              </div>
            )}

            {selectedAction && selectedActionPlanting && (
              <div className="calendar-action-detail-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) closeAction(); }}>
                <section className="calendar-action-detail-dialog" role="dialog" aria-modal="true" aria-labelledby={`calendar-action-detail-title-${selectedAction.id}`}>
                  <header>
                    <div><span>管理作業の詳細</span><h2 id={`calendar-action-detail-title-${selectedAction.id}`}>{selectedAction.title}</h2></div>
                    <button type="button" className="icon-button labeled-icon-button" data-calendar-dialog-close onClick={closeAction} aria-label="作業詳細を閉じる" title="閉じる"><X size={19} /><span>閉じる</span></button>
                  </header>
                  <div className="calendar-action-detail-body">
                    <CalendarActionCard
                      plantingId={selectedActionPlanting.id}
                      action={selectedAction}
                      actionType={actionTypeByCode.get(selectedAction.action_type) ?? actionTypeByCode.get("other") ?? FALLBACK_ACTION_TYPES[FALLBACK_ACTION_TYPES.length - 1]}
                      actionTypes={actionTypes}
                      timingState={suggestionByActionId.get(selectedAction.id)}
                      busy={calendarMutationBusy}
                      locked={generationLockActive}
                      initialRecording={recordActionId === selectedAction.id}
                      readiness={bundle.operation_readiness?.[selectedAction.id]}
                      viewer={bundle.viewer}
                      onEdit={onEditAction}
                      onComplete={onCompleteAction}
                      onReview={onReviewAction}
                      onSkip={onSkipAction}
                      onDelete={async (...args) => {
                        await onDeleteAction(...args);
                        closeAction();
                      }}
                    />
                  </div>
                </section>
              </div>
            )}
          </>
        )}
      </aside>
  );
  if (presentation === "page") return <main className="calendar-page-shell">{panel}</main>;
  return <div className="calendar-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>{panel}</div>;
}

function sortKanbanActions(
  actions: PlantCalendarAction[],
  column: KanbanColumn,
  timingByActionId: Map<string, ActionTimingState>,
) {
  return actions
    .filter((action) => actionKanbanColumn(action) === column)
    .sort((left, right) => compareManagementActions(left, right, timingByActionId));
}

function actionKanbanColumn(action: PlantCalendarAction): KanbanColumn {
  if (action.status === "planned") return "planned";
  if (action.status === "in_progress") return "in_progress";
  if (action.status === "awaiting_review") return "awaiting_review";
  return "completed";
}

function canDropAction(action: PlantCalendarAction, destination: KanbanColumn): boolean {
  if (destination === "planned") return action.status === "in_progress" || action.status === "skipped";
  if (destination === "in_progress") return action.status === "planned";
  if (destination === "awaiting_review") return action.status === "planned" || action.status === "in_progress";
  return false;
}

function compareManagementActions(
  left: PlantCalendarAction,
  right: PlantCalendarAction,
  timingByActionId: Map<string, ActionTimingState>,
) {
  const statusOrder = { planned: 0, in_progress: 1, awaiting_review: 2, completed: 3, skipped: 4 };
  const statusDifference = statusOrder[left.status] - statusOrder[right.status];
  if (statusDifference !== 0) return statusDifference;

  if ((left.status === "planned" || left.status === "in_progress") && left.status === right.status) {
    const leftTiming = timingByActionId.get(left.id);
    const rightTiming = timingByActionId.get(right.id);
    const timingDifference = (leftTiming ? TIMING_SORT_ORDER[leftTiming] : 3) - (rightTiming ? TIMING_SORT_ORDER[rightTiming] : 3);
    if (timingDifference !== 0) return timingDifference;
    const priorityDifference = PRIORITY_SORT_ORDER[left.priority] - PRIORITY_SORT_ORDER[right.priority];
    if (priorityDifference !== 0) return priorityDifference;
    return left.window_start.localeCompare(right.window_start) || left.window_end.localeCompare(right.window_end);
  }

  const leftDate = left.completion?.performed_on || left.skip_decision?.decided_on || left.window_end;
  const rightDate = right.completion?.performed_on || right.skip_decision?.decided_on || right.window_end;
  return rightDate.localeCompare(leftDate) || right.window_end.localeCompare(left.window_end);
}

function formatPersonHours(actions: PlantCalendarAction[]): string {
  const totalMinutes = actions.reduce((total, action) => total + action.required_people * action.estimated_minutes, 0);
  const hours = totalMinutes / 60;
  return Number.isInteger(hours) ? String(hours) : hours.toFixed(1);
}

function normalizeActionSearch(value: string): string {
  return value.normalize("NFKC").toLocaleLowerCase("ja-JP").replace(/[\s　]+/g, " ").trim();
}

function memberAssignmentScope(email: string): AssignmentScope {
  return `member:${email.toLocaleLowerCase()}`;
}

function buildMemberTaskSummaries(actions: PlantCalendarAction[], workLogs: PlantBundle["work_logs"]): MemberTaskSummary[] {
  const memberEmails = new Set<string>();
  actions.forEach((action) => {
    if (action.assigned_to) memberEmails.add(action.assigned_to.toLocaleLowerCase());
  });
  workLogs.forEach((workLog) => {
    if (workLog.performed_by) memberEmails.add(workLog.performed_by.toLocaleLowerCase());
  });
  return [...memberEmails]
    .map((email) => {
      const memberLogs = workLogs.filter((workLog) => workLog.performed_by.toLocaleLowerCase() === email);
      const approvedLogs = memberLogs.filter((workLog) => workLog.review_status === "approved");
      return {
        email,
        approvedCount: approvedLogs.length,
        pendingCount: memberLogs.filter((workLog) => workLog.review_status === "pending").length,
        latestApprovedOn: approvedLogs.map((workLog) => workLog.performed_on).sort().at(-1) ?? "",
      };
    })
    .sort((left, right) => (
      right.approvedCount - left.approvedCount
      || right.pendingCount - left.pendingCount
      || left.email.localeCompare(right.email)
    ));
}

function MemberTaskCompletionSummary({ summaries, selectedScope, teamView, onSelect }: {
  summaries: MemberTaskSummary[];
  selectedScope: AssignmentScope;
  teamView: boolean;
  onSelect: (email: string) => void;
}) {
  return (
    <section className="member-task-summary" aria-label={teamView ? "メンバー別の完遂状況" : "あなたの作業実績"}>
      <header>
        <span><UsersRound size={18} /></span>
        <div><strong>{teamView ? "メンバー別の完遂状況" : "あなたの作業実績"}</strong><small>管理者が承認した作業だけを「完遂」に集計</small></div>
      </header>
      {summaries.length > 0 ? (
        <div className="member-task-summary-list">
          {summaries.map((summary) => {
            const selected = selectedScope === memberAssignmentScope(summary.email);
            const achievement = taskAchievement(summary.approvedCount);
            return (
              <button
                key={summary.email}
                type="button"
                data-member-email={summary.email}
                className={selected ? "selected" : ""}
                aria-pressed={selected}
                onClick={() => onSelect(summary.email)}
              >
                <span className={`member-achievement-icon ${summary.approvedCount > 0 ? "achieved" : ""}`}><Trophy size={18} /></span>
                <span className="member-achievement-copy"><small>現在の称号</small><em>{achievement.currentTitle}</em></span>
                <strong>{teamView ? summary.email : "自分の完遂記録"}</strong>
                <span className="member-task-counts">
                  <span className="member-task-count"><b>{summary.approvedCount}</b>件 完遂</span>
                  <span className={`member-task-count ${summary.pendingCount > 0 ? "pending" : "quiet"}`}><b>{summary.pendingCount}</b>件 確認待ち</span>
                </span>
                <span className="member-achievement-progress" aria-label={achievement.nextLabel}>
                  <i><i style={{ width: `${achievement.progressPercent}%` }} /></i>
                  <small>{achievement.nextLabel}</small>
                </span>
                <small className="member-latest-completion">{summary.latestApprovedOn ? `最新実施 ${formatDate(summary.latestApprovedOn)}` : "最初の承認を待っています"}</small>
              </button>
            );
          })}
        </div>
      ) : <p>認証済みメンバーの提出記録はまだありません。</p>}
      <footer>速さや順位ではなく、承認済みの積み重ねを表示します。報酬額や送金状態はまだ扱いません。</footer>
    </section>
  );
}

const TASK_ACHIEVEMENTS = [
  { count: 1, title: "最初の一歩" },
  { count: 3, title: "着実な実践者" },
  { count: 5, title: "頼れるメンバー" },
  { count: 10, title: "圃場の達人" },
  { count: 20, title: "継続の名手" },
] as const;

function taskAchievement(approvedCount: number) {
  const current = [...TASK_ACHIEVEMENTS].reverse().find((achievement) => approvedCount >= achievement.count);
  const next = TASK_ACHIEVEMENTS.find((achievement) => approvedCount < achievement.count);
  return {
    currentTitle: current?.title ?? "スタート地点",
    progressPercent: next ? Math.round(approvedCount / next.count * 100) : 100,
    nextLabel: next ? `あと${next.count - approvedCount}件で「${next.title}」` : "すべての節目を達成しました",
  };
}

function KanbanEmptyState({ column }: { column: KanbanColumn }) {
  const message = column === "planned"
    ? "着手待ちの作業はありません。"
    : column === "in_progress"
      ? "作業中の項目はありません。"
      : column === "awaiting_review"
        ? "管理者の確認を待つ作業はありません。"
        : "完了した作業はありません。";
  return <p className="calendar-kanban-empty">{message}</p>;
}

function CalendarEmptyState() {
  return (
    <div className="calendar-empty">
      <Leaf size={32} />
      <strong>定植情報がありません</strong>
      <p>設置ビューで鉢や畝を選び、作物を登録するとカレンダーが作成されます。</p>
    </div>
  );
}

function SuggestionSummary({ suggestions }: { suggestions: PlantBundle["suggestions"] }) {
  const count = (state: PlantBundle["suggestions"][number]["timing_state"]) => suggestions.filter((item) => item.timing_state === state).length;
  return (
    <section className="suggestion-summary" aria-label="現在の提案">
      <span><strong>{count("overdue")}</strong>期限超過</span>
      <span><strong>{count("due")}</strong>今やる</span>
      <span><strong>{count("upcoming")}</strong>まもなく</span>
    </section>
  );
}

const FERTILIZER_KIND_OPTIONS: Array<{ value: FertilizerMaterialKind; label: string }> = [
  { value: "cattle_manure", label: "牛ふん堆肥" },
  { value: "poultry_manure", label: "鶏ふん・鶏ふん堆肥" },
  { value: "compost", label: "植物性堆肥・その他堆肥" },
  { value: "organic_fertilizer", label: "有機質肥料" },
  { value: "chemical_fertilizer", label: "化成・無機質肥料" },
  { value: "custom", label: "その他・独自資材" },
];

interface FertilizerDraft {
  materialId: string;
  appliedOn: string;
  materialKind: FertilizerMaterialKind;
  materialName: string;
  amountKg: string;
  nPercent: string;
  pPercent: string;
  kPercent: string;
  mgoPercent: string;
  annualAvailablePercent: string;
  effectYears: string;
  startDelayDays: string;
  analysisSource: string;
  notes: string;
}

function newFertilizerDraft(materials: FertilizerMaterial[]): FertilizerDraft {
  const material = materials[0];
  return {
    materialId: material?.id ?? "",
    appliedOn: todayString(),
    materialKind: material?.material_kind ?? "custom",
    materialName: material?.material_name ?? "",
    amountKg: "",
    nPercent: String(material?.nutrient_percent.n ?? ""),
    pPercent: String(material?.nutrient_percent.p2o5 ?? ""),
    kPercent: String(material?.nutrient_percent.k2o ?? ""),
    mgoPercent: String(material?.nutrient_percent.mgo ?? ""),
    annualAvailablePercent: String(material?.annual_available_percent ?? 50),
    effectYears: String(material?.effect_years ?? 1),
    startDelayDays: String(material?.start_delay_days ?? 0),
    analysisSource: material?.analysis_source ?? "",
    notes: "",
  };
}

function FertilizerEffectPanel({
  plantingId,
  placementName,
  applications,
  materials,
  busy,
  locked,
  onAdd,
  onDelete,
  onSaveMaterial,
  onDeleteMaterial,
}: {
  plantingId: string;
  placementName: string;
  applications: FertilizerApplication[];
  materials: FertilizerMaterial[];
  busy: boolean;
  locked: boolean;
  onAdd: (plantingId: string, payload: Record<string, unknown>) => Promise<void>;
  onDelete: (plantingId: string, applicationId: string) => Promise<void>;
  onSaveMaterial: (materialId: string, payload: Record<string, unknown>) => Promise<void>;
  onDeleteMaterial: (materialId: string) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [catalogOpen, setCatalogOpen] = useState(false);
  const [draft, setDraft] = useState<FertilizerDraft>(() => newFertilizerDraft(materials));
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [deletingApplicationId, setDeletingApplicationId] = useState("");
  const estimate = useMemo(() => summarizeFertilizerApplications(applications), [applications]);
  const selectedMaterial = materials.find((material) => material.id === draft.materialId);
  const change = <Key extends keyof FertilizerDraft>(key: Key, value: FertilizerDraft[Key]) => (
    setDraft((current) => ({ ...current, [key]: value }))
  );

  useEffect(() => {
    if (!locked) return;
    setEditing(false);
    setError("");
  }, [locked]);

  const applyMaterial = (materialId: string) => {
    const material = materials.find((item) => item.id === materialId);
    if (!material) return;
    setDraft((current) => ({
      ...current,
      materialId: material.id,
      materialKind: material.material_kind,
      materialName: material.material_name,
      nPercent: String(material.nutrient_percent.n),
      pPercent: String(material.nutrient_percent.p2o5),
      kPercent: String(material.nutrient_percent.k2o),
      mgoPercent: String(material.nutrient_percent.mgo),
      annualAvailablePercent: String(material.annual_available_percent),
      effectYears: String(material.effect_years),
      startDelayDays: String(material.start_delay_days),
      analysisSource: material.analysis_source,
    }));
  };

  const selectKind = (kind: FertilizerMaterialKind) => {
    const matching = materials.find((material) => material.material_kind === kind);
    if (matching) applyMaterial(matching.id);
    else setDraft((current) => ({ ...current, materialId: "", materialKind: kind }));
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    const nutrientValues = [draft.nPercent, draft.pPercent, draft.kPercent, draft.mgoPercent].map(Number);
    if (!nutrientValues.some((value) => value > 0)) {
      setError("製品表示や分析表から、N・P₂O₅・K₂O・MgO（苦土）のいずれかを入力してください。");
      return;
    }
    setSubmitting(true);
    try {
      await onAdd(plantingId, {
        material_id: draft.materialId,
        applied_on: draft.appliedOn,
        material_kind: draft.materialKind,
        material_name: draft.materialName,
        amount_kg: Number(draft.amountKg),
        nutrient_percent: { n: nutrientValues[0], p2o5: nutrientValues[1], k2o: nutrientValues[2], mgo: nutrientValues[3] },
        annual_available_percent: Number(draft.annualAvailablePercent),
        effect_years: Number(draft.effectYears),
        start_delay_days: Number(draft.startDelayDays),
        analysis_source: draft.analysisSource,
        notes: draft.notes,
      });
      setDraft(newFertilizerDraft(materials));
      setEditing(false);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setSubmitting(false);
    }
  };

  const deleteApplication = async (application: FertilizerApplication) => {
    if (!window.confirm(`${application.material_name}の施肥履歴を削除しますか？`)) return;
    setDeletingApplicationId(application.id);
    try {
      await onDelete(plantingId, application.id);
    } finally {
      setDeletingApplicationId("");
    }
  };

  return (
    <section className="fertilizer-effect-panel" aria-label="培地の施肥履歴と肥効見込み">
      <div className="calendar-section-heading">
        <div><Beaker size={17} /><strong>培地の施肥と残存肥効</strong><span>{placementName}</span></div>
        <div className="fertilizer-heading-actions">
          <button type="button" disabled={busy} onClick={() => setCatalogOpen(true)}>肥料カタログ</button>
          {!editing && <button type="button" disabled={busy} title={locked ? "AI栽培計画の作成が完了すると追加できます" : "施肥履歴をモーダルで追加"} onClick={() => { setDraft(newFertilizerDraft(materials)); setEditing(true); }}><Plus size={15} />施肥履歴を追加</button>}
        </div>
      </div>
      {applications.length === 0 ? (
        <p className="fertilizer-empty">この培地の施肥履歴は未登録です。元肥や堆肥を登録すると、AI計画が残存肥効を考慮します。</p>
      ) : (
        <>
          <div className="fertilizer-balance" aria-label="推定残存養分">
            {(["n", "p2o5", "k2o", "mgo"] as const).map((key) => (
              <div key={key}><span>{nutrientLabel(key)}</span><strong>{formatNutrientKg(estimate[key].remaining)}</strong><small>期間内の残存見込み</small></div>
            ))}
          </div>
          <div className="fertilizer-history-list">
            {[...applications].sort((left, right) => right.applied_on.localeCompare(left.applied_on)).map((application) => {
              const effect = fertilizerApplicationEstimate(application);
              return (
                <article key={application.id}>
                  <div><strong>{application.material_name}</strong><span>{fertilizerKindLabel(application.material_kind)} / {formatDate(application.applied_on)} / {application.amount_kg.toLocaleString("ja-JP", { maximumFractionDigits: 3 })} kg / {fertilizerCompositionLabel(application)}</span></div>
                  <div className="fertilizer-effect-window"><span style={{ width: `${effect.progressPercent}%` }} /><small>{formatDate(effect.start)}〜{formatDate(effect.end)} / 年間肥効率 {application.annual_available_percent}%</small></div>
                  <button
                    type="button"
                    disabled={busy || Boolean(deletingApplicationId)}
                    aria-busy={deletingApplicationId === application.id}
                    title="この施肥履歴を削除"
                    onClick={() => void deleteApplication(application)}
                  ><Trash2 size={14} />{deletingApplicationId === application.id ? "削除しています" : "削除"}</button>
                </article>
              );
            })}
          </div>
        </>
      )}
      <p className="fertilizer-caution">概算値です。製品分析値・地域の施肥基準・土壌分析・EC・葉色・樹勢・収穫品質を優先し、残効が不明なまま追加施肥しないでください。</p>
      {applications.length > 0 && <p className="fertilizer-regenerate-note">施肥履歴を追加・削除した後は「AI栽培計画を作り直す」から変更案を作ると、12か月計画へ反映できます。</p>}
      {editing && (
        <ModalDialog title="施肥履歴を追加" eyebrow={`${placementName}の培地へ実際に入れた肥料を記録`} onClose={() => { setEditing(false); setError(""); }} className="fertilizer-entry-dialog" size="wide">
          <form className="fertilizer-entry-form" data-fertilizer-form onSubmit={(event) => void submit(event)}>
          <div className="fertilizer-form-intro"><strong>実際に入れた肥料を記録</strong><span>製品kgと養分kgを分けて計算します。</span></div>
          <div className="fertilizer-preset-picker">
            <label>肥料カタログ<select name="fertilizer_material" value={draft.materialId} onChange={(event) => applyMaterial(event.target.value)}>
              <optgroup label="一般的な肥料">{materials.filter((material) => material.scope === "builtin").map((material) => <option key={material.id} value={material.id}>{material.label}</option>)}</optgroup>
              {materials.some((material) => material.scope === "user") && <optgroup label="登録した肥料">{materials.filter((material) => material.scope === "user").map((material) => <option key={material.id} value={material.id}>{material.label}</option>)}</optgroup>}
            </select></label>
            <div aria-live="polite">
              <strong>{selectedMaterial?.label ?? "製品ラベルから入力"}</strong>
              <span>{selectedMaterial?.summary}</span>
              <small>一般値は編集可能な開始値です。手元の袋・分析表に値があれば必ず上書きしてください。</small>
              {selectedMaterial?.source_url && <a href={selectedMaterial.source_url} target="_blank" rel="noreferrer">参考資料を別タブで確認</a>}
            </div>
          </div>
          <div className="fertilizer-form-grid three">
            <label>施肥日<input name="applied_on" type="date" required max={todayString()} value={draft.appliedOn} onChange={(event) => change("appliedOn", event.target.value)} /></label>
            <label>資材の種類<select name="material_kind" value={draft.materialKind} onChange={(event) => selectKind(event.target.value as FertilizerMaterialKind)}>{FERTILIZER_KIND_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
            <label>投入量（kg）<input name="amount_kg" type="number" required min="0.001" max="1000000" step="0.001" value={draft.amountKg} onChange={(event) => change("amountKg", event.target.value)} /></label>
          </div>
          <label>資材・製品名<input name="material_name" required maxLength={180} value={draft.materialName} onChange={(event) => change("materialName", event.target.value)} placeholder="袋や分析表に記載された名称" /></label>
          <fieldset><legend>袋・分析表の保証成分（製品重量に対する%）</legend><div className="fertilizer-form-grid four">
            <label>N<input name="n_percent" type="number" min="0" max="100" step="0.01" value={draft.nPercent} onChange={(event) => change("nPercent", event.target.value)} /></label>
            <label>P₂O₅<input name="p2o5_percent" type="number" min="0" max="100" step="0.01" value={draft.pPercent} onChange={(event) => change("pPercent", event.target.value)} /></label>
            <label>K₂O<input name="k2o_percent" type="number" min="0" max="100" step="0.01" value={draft.kPercent} onChange={(event) => change("kPercent", event.target.value)} /></label>
            <label>MgO（苦土）<input name="mgo_percent" type="number" min="0" max="100" step="0.01" value={draft.mgoPercent} onChange={(event) => change("mgoPercent", event.target.value)} /></label>
          </div></fieldset>
          <fieldset><legend>肥効の見積条件</legend><div className="fertilizer-form-grid three">
            <label>Nを基準にした年間肥効率（概算%）<input name="annual_available_percent" type="number" required min="0.1" max="100" step="0.1" value={draft.annualAvailablePercent} onChange={(event) => change("annualAvailablePercent", event.target.value)} /><small>{selectedMaterial?.label ?? "選択した資材"}の{draft.annualAvailablePercent}%は編集可能な開始値です。</small></label>
            <label>肥効を見込む年数<input name="effect_years" type="number" required min="1" max="10" step="1" value={draft.effectYears} onChange={(event) => change("effectYears", event.target.value)} /></label>
            <label>効き始めるまで（日）<input name="start_delay_days" type="number" required min="0" max="3650" step="1" value={draft.startDelayDays} onChange={(event) => change("startDelayDays", event.target.value)} /></label>
          </div></fieldset>
          <p className="fertilizer-estimate-note">P₂O₅・K₂O・MgOはNと肥効率が異なることがあります。この画面の残効は安全側の概算として使い、地域の施肥基準と土壌分析を優先してください。</p>
          <label>成分・肥効率の根拠<input maxLength={500} value={draft.analysisSource} onChange={(event) => change("analysisSource", event.target.value)} placeholder="製品ラベル、分析表、地域施肥基準など" /></label>
          <label>メモ<textarea maxLength={1000} value={draft.notes} onChange={(event) => change("notes", event.target.value)} placeholder="全面施用、畝内混和、施用範囲など" /></label>
          {error && <p className="form-error" role="alert">{error}</p>}
          <div className="form-actions"><button type="button" onClick={() => { setEditing(false); setError(""); }}>キャンセル</button><button type="submit" disabled={busy || submitting} aria-busy={submitting}>{submitting ? "履歴を保存しています" : "履歴と肥効を保存"}</button></div>
          </form>
        </ModalDialog>
      )}
      {catalogOpen && (
        <FertilizerCatalogDialog
          materials={materials}
          busy={busy}
          onClose={() => setCatalogOpen(false)}
          onSave={onSaveMaterial}
          onDelete={onDeleteMaterial}
        />
      )}
    </section>
  );
}

interface FertilizerCatalogDraft {
  id: string;
  label: string;
  summary: string;
  materialKind: FertilizerMaterialKind;
  materialName: string;
  nPercent: string;
  pPercent: string;
  kPercent: string;
  mgoPercent: string;
  annualAvailablePercent: string;
  effectYears: string;
  startDelayDays: string;
  analysisSource: string;
  sourceUrl: string;
}

function fertilizerCatalogDraft(material?: FertilizerMaterial): FertilizerCatalogDraft {
  return {
    id: material?.id ?? "",
    label: material?.label ?? "",
    summary: material?.summary ?? "",
    materialKind: material?.material_kind ?? "custom",
    materialName: material?.material_name ?? "",
    nPercent: String(material?.nutrient_percent.n ?? ""),
    pPercent: String(material?.nutrient_percent.p2o5 ?? ""),
    kPercent: String(material?.nutrient_percent.k2o ?? ""),
    mgoPercent: String(material?.nutrient_percent.mgo ?? ""),
    annualAvailablePercent: String(material?.annual_available_percent ?? 50),
    effectYears: String(material?.effect_years ?? 1),
    startDelayDays: String(material?.start_delay_days ?? 7),
    analysisSource: material?.analysis_source ?? "製品ラベル",
    sourceUrl: material?.source_url ?? "",
  };
}

function FertilizerCatalogDialog({
  materials,
  busy,
  onClose,
  onSave,
  onDelete,
}: {
  materials: FertilizerMaterial[];
  busy: boolean;
  onClose: () => void;
  onSave: (materialId: string, payload: Record<string, unknown>) => Promise<void>;
  onDelete: (materialId: string) => Promise<void>;
}) {
  const [draft, setDraft] = useState<FertilizerCatalogDraft | null>(null);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [deletingMaterialId, setDeletingMaterialId] = useState("");
  const customMaterials = materials.filter((material) => material.scope === "user");
  const change = <Key extends keyof FertilizerCatalogDraft>(key: Key, value: FertilizerCatalogDraft[Key]) => (
    setDraft((current) => current ? { ...current, [key]: value } : current)
  );
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!draft) return;
    setError("");
    const nutrients = [draft.nPercent, draft.pPercent, draft.kPercent, draft.mgoPercent].map(Number);
    if (!nutrients.some((value) => value > 0)) {
      setError("袋の表示を見て、N・P₂O₅・K₂O・MgO（苦土）のいずれかを入力してください。");
      return;
    }
    setSubmitting(true);
    try {
      await onSave(draft.id, {
        label: draft.label,
        summary: draft.summary,
        material_kind: draft.materialKind,
        material_name: draft.materialName,
        nutrient_percent: { n: nutrients[0], p2o5: nutrients[1], k2o: nutrients[2], mgo: nutrients[3] },
        annual_available_percent: Number(draft.annualAvailablePercent),
        effect_years: Number(draft.effectYears),
        start_delay_days: Number(draft.startDelayDays),
        analysis_source: draft.analysisSource,
        source_url: draft.sourceUrl,
      });
      setDraft(null);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setSubmitting(false);
    }
  };

  const deleteMaterial = async (material: FertilizerMaterial) => {
    if (!window.confirm(`${material.label}をカタログから削除しますか？\n過去の施肥履歴は残ります。`)) return;
    setDeletingMaterialId(material.id);
    try {
      await onDelete(material.id);
    } finally {
      setDeletingMaterialId("");
    }
  };

  return (
    <ModalDialog title="肥料カタログ" eyebrow="よく使う肥料を選びやすくする" onClose={onClose} className="fertilizer-catalog-dialog" size="wide">
      <div className="fertilizer-catalog-intro">
        <div className="fertilizer-bag-illustration" aria-hidden="true"><PackageOpen size={25} /></div>
        <div><strong>袋の表示を登録すると、次回から選ぶだけ</strong><span>一般値は目安です。実際の製品ラベルや分析結果を優先します。</span></div>
        {!draft && <button type="button" onClick={() => setDraft(fertilizerCatalogDraft())}><Plus size={15} />自分の肥料を追加</button>}
      </div>
      {!draft ? (
        <div className="fertilizer-catalog-sections">
          <section><h3>一般的な肥料</h3><div className="fertilizer-catalog-grid">{materials.filter((material) => material.scope === "builtin").map((material) => <FertilizerMaterialCard key={material.id} material={material} />)}</div></section>
          <section><h3>登録した肥料 <span>{customMaterials.length}件</span></h3>{customMaterials.length === 0 ? <p className="fertilizer-empty">製品袋の成分を登録すると、施肥記録で何度でも使えます。</p> : <div className="fertilizer-catalog-grid">{customMaterials.map((material) => (
            <FertilizerMaterialCard key={material.id} material={material} actions={
              <><button type="button" disabled={Boolean(deletingMaterialId)} onClick={() => setDraft(fertilizerCatalogDraft(material))}>編集</button><button type="button" className="danger" disabled={busy || Boolean(deletingMaterialId)} aria-busy={deletingMaterialId === material.id} onClick={() => void deleteMaterial(material)}>{deletingMaterialId === material.id ? "削除しています" : "削除"}</button></>
            } />
          ))}</div>}</section>
        </div>
      ) : (
        <form className="fertilizer-entry-form fertilizer-catalog-form" onSubmit={(event) => void submit(event)}>
          <div className="fertilizer-form-intro"><strong>{draft.id ? "登録した肥料を編集" : "肥料袋の情報を登録"}</strong><span>まず袋の表にある名前とN-P-Kを写します。</span></div>
          <div className="fertilizer-form-grid three">
            <label>選ぶときの名前<input required maxLength={180} value={draft.label} onChange={(event) => change("label", event.target.value)} placeholder="例：いちご用 有機配合" /></label>
            <label>袋に書かれた製品名<input required maxLength={180} value={draft.materialName} onChange={(event) => change("materialName", event.target.value)} /></label>
            <label>種類<select value={draft.materialKind} onChange={(event) => change("materialKind", event.target.value as FertilizerMaterialKind)}>{FERTILIZER_KIND_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
          </div>
          <label>ひとこと説明<input maxLength={500} value={draft.summary} onChange={(event) => change("summary", event.target.value)} placeholder="例：元肥に使う、ゆっくり効く" /></label>
          <fieldset><legend>袋の「保証成分量」（%）</legend><div className="fertilizer-form-grid four">
            <label>N<input type="number" min="0" max="100" step="0.01" value={draft.nPercent} onChange={(event) => change("nPercent", event.target.value)} /></label>
            <label>P₂O₅<input type="number" min="0" max="100" step="0.01" value={draft.pPercent} onChange={(event) => change("pPercent", event.target.value)} /></label>
            <label>K₂O<input type="number" min="0" max="100" step="0.01" value={draft.kPercent} onChange={(event) => change("kPercent", event.target.value)} /></label>
            <label>MgO（苦土）<input type="number" min="0" max="100" step="0.01" value={draft.mgoPercent} onChange={(event) => change("mgoPercent", event.target.value)} /></label>
          </div></fieldset>
          <details className="fertilizer-advanced-fields"><summary>肥効の見積りを調整（上級者向け）</summary><div className="fertilizer-form-grid three">
            <label>年間肥効率（%）<input type="number" required min="0.1" max="100" step="0.1" value={draft.annualAvailablePercent} onChange={(event) => change("annualAvailablePercent", event.target.value)} /></label>
            <label>肥効を見込む年数<input type="number" required min="1" max="10" value={draft.effectYears} onChange={(event) => change("effectYears", event.target.value)} /></label>
            <label>効き始めるまで（日）<input type="number" required min="0" max="3650" value={draft.startDelayDays} onChange={(event) => change("startDelayDays", event.target.value)} /></label>
            <label>数値の根拠<input maxLength={500} value={draft.analysisSource} onChange={(event) => change("analysisSource", event.target.value)} /></label>
            <label>参考URL<input type="url" maxLength={1000} value={draft.sourceUrl} onChange={(event) => change("sourceUrl", event.target.value)} /></label>
          </div></details>
          {error && <p className="form-error" role="alert">{error}</p>}
          <div className="form-actions"><button type="button" onClick={() => { setDraft(null); setError(""); }}>一覧へ戻る</button><button type="submit" disabled={busy || submitting} aria-busy={submitting}>{submitting ? "保存しています" : draft.id ? "変更を保存" : "カタログへ追加"}</button></div>
        </form>
      )}
    </ModalDialog>
  );
}

function FertilizerMaterialCard({ material, actions }: { material: FertilizerMaterial; actions?: ReactNode }) {
  const MaterialIcon = material.material_kind === "chemical_fertilizer"
    ? Zap
    : material.material_kind === "cattle_manure" || material.material_kind === "poultry_manure"
      ? Wheat
      : material.material_kind === "compost"
        ? Sprout
        : Leaf;
  return (
    <article className="fertilizer-material-card">
      <div className={`fertilizer-material-icon kind-${material.material_kind}`} aria-hidden="true"><MaterialIcon size={21} /></div>
      <div><strong>{material.label}</strong><span>{material.summary || fertilizerKindLabel(material.material_kind)}</span><small>N {material.nutrient_percent.n}%・P {material.nutrient_percent.p2o5}%・K {material.nutrient_percent.k2o}% / 効き始め 約{material.start_delay_days}日</small></div>
      {actions && <footer>{actions}</footer>}
    </article>
  );
}

function fertilizerApplicationEstimate(application: FertilizerApplication) {
  const applied = new Date(`${application.applied_on}T00:00:00`);
  const startDate = new Date(applied);
  startDate.setDate(startDate.getDate() + application.start_delay_days);
  const endDate = new Date(startDate);
  endDate.setDate(endDate.getDate() + application.effect_years * 365);
  const totalDuration = Math.max(1, endDate.getTime() - startDate.getTime());
  const progress = Math.max(0, Math.min(1, (Date.now() - startDate.getTime()) / totalDuration));
  const effectiveFraction = Math.min(1, application.annual_available_percent / 100 * application.effect_years);
  const nutrients = Object.fromEntries((["n", "p2o5", "k2o", "mgo"] as const).map((key) => {
    const total = application.amount_kg * (application.nutrient_percent[key] ?? 0) / 100 * effectiveFraction;
    return [key, { total, remaining: total * (1 - progress) }];
  })) as Record<"n" | "p2o5" | "k2o" | "mgo", { total: number; remaining: number }>;
  return { start: dateString(startDate), end: dateString(endDate), progressPercent: Math.round(progress * 100), nutrients };
}

function summarizeFertilizerApplications(applications: FertilizerApplication[]) {
  const result = { n: { remaining: 0 }, p2o5: { remaining: 0 }, k2o: { remaining: 0 }, mgo: { remaining: 0 } };
  applications.forEach((application) => {
    const estimate = fertilizerApplicationEstimate(application);
    (["n", "p2o5", "k2o", "mgo"] as const).forEach((key) => { result[key].remaining += estimate.nutrients[key].remaining; });
  });
  return result;
}

function nutrientLabel(key: "n" | "p2o5" | "k2o" | "mgo") {
  return key === "n" ? "N" : key === "p2o5" ? "P₂O₅" : key === "k2o" ? "K₂O" : "MgO（苦土）";
}

function fertilizerCompositionLabel(application: FertilizerApplication) {
  return (["n", "p2o5", "k2o", "mgo"] as const)
    .map((key) => `${nutrientLabel(key)} ${application.nutrient_percent[key] ?? 0}%`)
    .join(" / ");
}

function fertilizerKindLabel(kind: FertilizerMaterialKind) {
  return FERTILIZER_KIND_OPTIONS.find((option) => option.value === kind)?.label ?? "その他の肥料";
}

function dateString(value: Date) {
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
}

function formatNutrientKg(value: number) {
  if (value >= 1) return `${value.toFixed(2)} kg`;
  return `${Math.round(value * 1000)} g`;
}

function CareProfileSummary({ calendar }: { calendar: PlantCalendar }) {
  const profile = calendar.care_profile;
  const rules = calendar.task_rules ?? [];
  const generationInputs = calendarGenerationInputItems(calendar);
  const [open, setOpen] = useState(false);
  if (!profile && rules.length === 0) return null;

  return (
    <section className="care-profile-summary">
      <button type="button" className="care-profile-trigger" onClick={() => setOpen(true)} aria-haspopup="dialog">
        <span className="care-profile-trigger-icon"><BookOpen size={20} /></span>
        <span><strong>栽培基準を見る</strong><small>Web資料をAIが実用的な管理基準に整理</small></span>
        <em>{rules.length}規則</em><ChevronRight size={18} />
      </button>
      {open && <ModalDialog title="栽培基準" eyebrow="根拠資料と現在の栽培条件から整理" onClose={() => setOpen(false)} className="care-profile-dialog" size="wide">
      <div className="care-profile-body">
        {profile?.summary && <p>{profile.summary}</p>}
        <dl>
          <div><dt>潅水</dt><dd>{profile?.irrigation?.strategy || "条件未設定"}<small>{formatInterval(profile?.irrigation?.baseline_interval_days)}</small></dd></div>
          <div><dt>施肥</dt><dd>{profile?.fertilization?.strategy || "条件未設定"}</dd></div>
          <div><dt>EC</dt><dd>{profile?.fertilization?.ec_management || "条件未設定"}</dd></div>
          <div><dt>pH</dt><dd>{profile?.fertilization?.ph_management || "条件未設定"}</dd></div>
        </dl>
        {rules.length > 0 && (
          <div className="care-rule-list">
            {rules.filter((rule) => rule.recurrence_type !== "one_time").slice(0, 8).map((rule) => (
              <div key={rule.rule_id}>
                <strong>{rule.title}</strong>
                <span>{formatInterval(rule.interval_days)}{rule.anchor === "completion_date" ? " / 実施日起点" : ""}</span>
              </div>
            ))}
          </div>
        )}
        {generationInputs.length > 0 && (
          <section className="care-inputs" aria-label="この計画に反映した情報">
            <strong>この計画に反映した情報</strong>
            <ul>{generationInputs.map((item) => <li key={item}>{item}</li>)}</ul>
            <small>生成時点の記録スナップショットです。新しい記録は次回の再計画で反映されます。</small>
          </section>
        )}
        {profile?.knowledge_evidence?.length > 0 && (
          <section className="care-evidence" aria-label="栽培根拠の出典">
            <strong>参考にした公的資料</strong>
            <ul>
              {profile.knowledge_evidence.map((source) => (
                <li key={source.url}>
                  <a href={source.url} target="_blank" rel="noopener noreferrer">{source.title}</a>
                  <small>{[source.publisher, source.applicable_region, source.published_at && `発行・改訂 ${source.published_at}`, source.fetched_at && `取得 ${source.fetched_at.slice(0, 10)}`].filter(Boolean).join(" / ")}</small>
                </li>
              ))}
            </ul>
          </section>
        )}
        {profile?.assumptions?.length > 0 && <p className="care-assumptions">前提: {profile.assumptions.join(" / ")}</p>}
      </div>
      </ModalDialog>}
    </section>
  );
}

function calendarGenerationInputItems(calendar: PlantCalendar): string[] {
  const snapshot = objectRecord(calendar.generation.context_snapshot);
  if (Object.keys(snapshot).length === 0) return [];
  const items: string[] = [];
  if (Object.keys(objectRecord(snapshot.planting)).length > 0 || Object.keys(objectRecord(snapshot.field)).length > 0) {
    items.push("作付け・圃場条件");
  }
  const fertilizerCount = arrayLength(objectRecord(snapshot.fertilizer_history).applications);
  const workLogCount = arrayLength(snapshot.recent_work_logs);
  const questionCount = arrayLength(snapshot.recent_questions);
  const evidenceCount = arrayLength(objectRecord(snapshot.crop_knowledge).sources);
  const guidanceCount = Number(calendar.generation.guidance_count || 0);
  if (fertilizerCount > 0) items.push(`施肥履歴 ${fertilizerCount}件`);
  if (workLogCount > 0) items.push(`作業記録 ${workLogCount}件`);
  if (questionCount > 0) items.push(`植物相談 ${questionCount}件`);
  if (evidenceCount > 0) items.push(`Web根拠 ${evidenceCount}件`);
  if (guidanceCount > 0) items.push(`利用者の修正例 ${guidanceCount}件`);
  return items;
}

function objectRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function arrayLength(value: unknown): number {
  return Array.isArray(value) ? value.length : 0;
}

function formatChatTime(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("ja-JP", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(parsed);
}

function formatInterval(interval?: { min: number | null; preferred: number | null; max: number | null }) {
  if (!interval) return "条件で判断";
  if (interval.preferred) return `標準 ${interval.preferred}日`;
  if (interval.min || interval.max) return `${interval.min ?? "?"}〜${interval.max ?? "?"}日`;
  return "条件で判断";
}

function regenerationChangeLabel(changeType: "add" | "update" | "delete") {
  if (changeType === "add") return "新しい作業を追加";
  if (changeType === "delete") return "現在の作業を削除";
  return "作業内容を変更";
}

function regenerationApproveLabel(changeType: "add" | "update" | "delete") {
  if (changeType === "add") return "この作業を追加する";
  if (changeType === "delete") return "この作業を削除する";
  return "この変更を取り入れる";
}

function calendarPlanningContext(calendar: PlantCalendar | null): Record<string, unknown> {
  const snapshot = calendar?.generation.context_snapshot;
  if (!snapshot || typeof snapshot.planning !== "object" || snapshot.planning === null) return {};
  return snapshot.planning as Record<string, unknown>;
}
