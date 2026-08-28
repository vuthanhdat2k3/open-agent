"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { OperatorSurface } from "./operator-surface";
import type { ApprovalRequest, CustomerIntelligenceNotification, CustomerIntelligenceCase } from "@/types";
import { useApprovals, useDecideApproval, useCustomerIntelligenceNotifications, useCustomerIntelligenceCases } from "@/hooks";
import { getWorkflowInstallations } from "@/lib/automations/api";
import { getCompanionConfig, type CompanionConfig, DEFAULT_COMPANION_CONFIG } from "@/lib/operator/companion-config";
import { createIdempotencyKey } from "@/lib/email-intelligence/idempotency";
import { toast } from "sonner";
import { useTranslation } from "@/lib/i18n";

interface Companion3DProps {
  initialApprovals?: ApprovalRequest[];
  initialNotifications?: CustomerIntelligenceNotification[];
  initialCases?: CustomerIntelligenceCase[];
}

export function Companion3D({
  initialApprovals,
  initialNotifications,
  initialCases,
}: Companion3DProps) {
    const { locale, tx } = useTranslation();
  const router = useRouter();
  const [config, setConfig] = React.useState<CompanionConfig>(DEFAULT_COMPANION_CONFIG);

  // Sync config from storage & events
  React.useEffect(() => {
    setConfig(getCompanionConfig());
    const handleUpdate = () => setConfig(getCompanionConfig());
    window.addEventListener("companion-config-updated", handleUpdate);
    return () => window.removeEventListener("companion-config-updated", handleUpdate);
  }, []);

  const approvalsQuery = useApprovals(config.enableApprovals);
  const notificationsQuery = useCustomerIntelligenceNotifications({ unreadOnly: true });
  const casesQuery = useCustomerIntelligenceCases({ limit: 5 });
  const installationsQuery = useQuery({
    queryKey: ["workflow-installations"],
    queryFn: getWorkflowInstallations,
    refetchInterval: 30_000,
  });
  const decideApprovalMutation = useDecideApproval();

  const approvals = approvalsQuery.data || initialApprovals || [];
  const notifications = notificationsQuery.data?.items || initialNotifications || [];
  const cases = casesQuery.data || initialCases || [];
  const installations = installationsQuery.data || [];
  const activeRoutinesCount = installations.filter((i) => i.status === "enabled").length || installations.length || 7;

  const [isOpen, setIsOpen] = React.useState(false);
  const [pos, setPos] = React.useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const [isInitialized, setIsInitialized] = React.useState(false);
  const [isDragging, setIsDragging] = React.useState(false);
  const [activeDock, setActiveDock] = React.useState<number | null>(null);

  const companionRef = React.useRef<HTMLDivElement>(null);
  const modelViewerRef = React.useRef<any>(null);
  const dragStartRef = React.useRef<{ x: number; y: number; startPosX: number; startPosY: number; hasMoved: boolean }>({
    x: 0,
    y: 0,
    startPosX: 0,
    startPosY: 0,
    hasMoved: false,
  });

  // Dynamic import of model-viewer
  React.useEffect(() => {
    if (typeof window === "undefined") return;
    if (!customElements.get("model-viewer")) {
      const script = document.createElement("script");
      script.type = "module";
      script.src = "https://unpkg.com/@google/model-viewer@4.1.0/dist/model-viewer.min.js";
      document.head.appendChild(script);
    }
  }, []);

  // Set default initial position based on config
  React.useEffect(() => {
    if (typeof window === "undefined" || isInitialized) return;
    let initialX = window.innerWidth - 95;
    let initialY = window.innerHeight - 95;

    if (config.defaultPosition === "top-right") {
      initialX = window.innerWidth - 95;
      initialY = 110;
    } else if (config.defaultPosition === "middle-right") {
      initialX = window.innerWidth - 95;
      initialY = window.innerHeight * 0.5;
    } else if (config.defaultPosition === "bottom-left") {
      initialX = 280;
      initialY = window.innerHeight - 95;
    }

    setPos({ x: initialX, y: initialY });
    setIsInitialized(true);
  }, [config.defaultPosition, isInitialized]);

  // Window resize handler to maintain relative position
  React.useEffect(() => {
    if (typeof window === "undefined") return;
    const handleResize = () => {
      setPos((prev) => ({
        x: Math.max(90, Math.min(window.innerWidth - 90, prev.x)),
        y: Math.max(90, Math.min(window.innerHeight - 90, prev.y)),
      }));
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  // Head look-at loop
  React.useEffect(() => {
    let targetTheta = 0;
    let currentTheta = 0;
    let targetPhi = 75;
    let currentPhi = 75;
    let animationFrameId: number;

    const handleMouseMove = (e: MouseEvent) => {
      if (isDragging || !companionRef.current) return;
      const r = companionRef.current.getBoundingClientRect();
      const dx = (e.clientX - (r.left + r.width / 2)) / window.innerWidth;
      const dy = (e.clientY - (r.top + r.height / 2)) / window.innerHeight;
      targetTheta = Math.max(-28, Math.min(28, dx * 65));
      targetPhi = Math.max(68, Math.min(84, 75 + dy * 22));
    };

    const renderLoop = () => {
      currentTheta += (targetTheta - currentTheta) * 0.12;
      currentPhi += (targetPhi - currentPhi) * 0.12;
      if (modelViewerRef.current && modelViewerRef.current.cameraOrbit !== undefined) {
        modelViewerRef.current.cameraOrbit = `${currentTheta.toFixed(1)}deg ${currentPhi.toFixed(1)}deg 2.4m`;
      }
      animationFrameId = requestAnimationFrame(renderLoop);
    };

    window.addEventListener("mousemove", handleMouseMove);
    animationFrameId = requestAnimationFrame(renderLoop);

    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      cancelAnimationFrame(animationFrameId);
    };
  }, [isDragging]);

  // Drag and Drop with Magnetic Snapping
  const handlePointerDown = (e: React.PointerEvent) => {
    if ((e.target as HTMLElement).closest("button, input, a, .thought-bubble")) return;
    setIsDragging(true);
    dragStartRef.current = {
      x: e.clientX,
      y: e.clientY,
      startPosX: pos.x,
      startPosY: pos.y,
      hasMoved: false,
    };
    if (isOpen) setIsOpen(false);
  };

  const handlePointerMove = (e: React.PointerEvent) => {
    if (!isDragging) return;
    const dx = e.clientX - dragStartRef.current.x;
    const dy = e.clientY - dragStartRef.current.y;
    if (Math.hypot(dx, dy) > 6) dragStartRef.current.hasMoved = true;

    const newX = Math.max(90, Math.min(window.innerWidth - 90, dragStartRef.current.startPosX + dx));
    const newY = Math.max(90, Math.min(window.innerHeight - 90, dragStartRef.current.startPosY + dy));
    setPos({ x: newX, y: newY });

    // Check dock proximity
    const docks = [
      { id: 0, x: window.innerWidth - 95, y: window.innerHeight - 95 },
      { id: 1, x: window.innerWidth - 95, y: 110 },
      { id: 2, x: window.innerWidth - 95, y: window.innerHeight * 0.5 },
      { id: 3, x: 280, y: window.innerHeight - 95 },
    ];
    let foundDock: number | null = null;
    for (const d of docks) {
      if (Math.hypot(newX - d.x, newY - d.y) < 80) {
        foundDock = d.id;
        break;
      }
    }
    setActiveDock(foundDock);
  };

  const handlePointerUp = () => {
    if (!isDragging) return;
    setIsDragging(false);

    // Snap to active dock
    const docks = [
      { id: 0, x: window.innerWidth - 95, y: window.innerHeight - 95 },
      { id: 1, x: window.innerWidth - 95, y: 110 },
      { id: 2, x: window.innerWidth - 95, y: window.innerHeight * 0.5 },
      { id: 3, x: 280, y: window.innerHeight - 95 },
    ];
    if (activeDock !== null && docks[activeDock]) {
      setPos({ x: docks[activeDock].x, y: docks[activeDock].y });
    }
    setActiveDock(null);
  };

  const handleDecideApproval = async (id: string, decision: "approved" | "rejected") => {
    try {
      await decideApprovalMutation.mutateAsync({
        id,
        decision,
        reason: decision === "approved" ? "Executive 1-Click Approval" : "User rejected via operator",
        idempotencyKey: createIdempotencyKey(),
      });
      toast.success(
        decision === "approved"
          ? tx("Đã phê duyệt và điều phối hành động thành công!", "Action approved and dispatched successfully!")
          : tx("Đã từ chối hành động an toàn.", "Action rejected safely."),
      );
    } catch (err: any) {
      toast.error(err.message || tx("Không thể xử lý phê duyệt.", "Failed to process approval."));
    }
  };

  const handleBatchDecideAll = async () => {
    if (approvals.length === 0) return;
    try {
      await Promise.all(
        approvals.map((app) =>
          decideApprovalMutation.mutateAsync({
            id: app.id,
            decision: "approved",
            reason: "Executive Batch 1-Click Approval",
            idempotencyKey: createIdempotencyKey(),
          }),
        ),
      );
      toast.success(tx(`Đã phê duyệt và điều phối tất cả ${approvals.length} hành động!`, `Successfully approved and dispatched all ${approvals.length} actions!`));
    } catch (err: any) {
      toast.error(err.message || tx("Không thể xử lý phê duyệt hàng loạt.", "Failed to process batch approval."));
    }
  };

  const handleSendDirection = (prompt: string) => {
    const lower = prompt.toLowerCase();
    if (lower.includes("approve all") || lower.includes("duyet")) {
      void handleBatchDecideAll();
      return;
    }
    const agentParam = config.brainAgentId ? `&agent=${encodeURIComponent(config.brainAgentId)}` : "";
    router.push(`/chat?prompt=${encodeURIComponent(prompt)}${agentParam}`);
    setIsOpen(false);
  };

  const anchorRect = companionRef.current?.getBoundingClientRect() || null;

  return (
    <>
      {/* Visual Magnetic Docking Target Guides (Active during drag) */}
      {isDragging && (
        <div className="pointer-events-none fixed inset-0 z-30 transition-opacity duration-300">
          {[
            { id: 0, label: tx("Dưới phải", "Bottom Right"), x: window.innerWidth - 110, y: window.innerHeight - 110 },
            { id: 1, label: tx("Trên phải", "Top Right"), x: window.innerWidth - 110, y: 120 },
            { id: 2, label: tx("Giữa phải", "Middle Right"), x: window.innerWidth - 110, y: window.innerHeight * 0.5 },
            { id: 3, label: tx("Dưới trái", "Bottom Left"), x: 290, y: window.innerHeight - 110 },
          ].map((dock) => {
            const isTarget = activeDock === dock.id;
            return (
              <div
                key={dock.id}
                style={{
                  left: `${dock.x}px`,
                  top: `${dock.y}px`,
                  transform: "translate(-50%, -50%)",
                }}
                className={`absolute flex h-24 w-24 items-center justify-center rounded-3xl border-2 transition-all duration-200 ${
                  isTarget
                    ? "scale-110 border-primary bg-primary/20 shadow-[0_0_25px_rgba(59,130,246,0.5)] ring-4 ring-primary/30"
                    : "border-dashed border-muted-foreground/30 bg-card/20 backdrop-blur-xs"
                }`}
              >
                <div className="flex flex-col items-center gap-1 text-center">
                  <span className={`h-2.5 w-2.5 rounded-full ${isTarget ? "bg-primary animate-ping" : "bg-muted-foreground/40"}`} />
                  <span className="font-mono text-[9px] uppercase tracking-wider text-muted-foreground">
                    {dock.label}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* 3D Companion Avatar Container */}
      <div
        id="companion-trigger"
        ref={companionRef}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        style={{
          position: "fixed",
          left: `${pos.x}px`,
          top: `${pos.y}px`,
          width: "190px",
          height: "185px",
          transform: "translate(-50%, -50%)",
          zIndex: isDragging ? 45 : 35,
          cursor: isDragging ? "grabbing" : "grab",
          touchAction: "none",
          userSelect: "none",
        }}
        onClick={() => {
          if (dragStartRef.current.hasMoved) {
            dragStartRef.current.hasMoved = false;
            return;
          }
          setIsOpen(!isOpen);
        }}
        className={`group focus:outline-none transition-transform duration-200 ${
          isOpen ? "scale-105" : "hover:scale-102"
        }`}
      >
        {/* Floating Living Thought Bubble Above Head */}
        {config.showThoughtBubbles && approvals.length > 0 && (
          <div
            onClick={(e) => {
              e.stopPropagation();
              setIsOpen(true);
            }}
            className="thought-bubble animate-bounce-subtle pointer-events-auto absolute -top-9 left-1/2 flex -translate-x-1/2 cursor-pointer items-center gap-2 whitespace-nowrap rounded-full border border-amber-500/50 bg-card/95 px-3.5 py-1 text-[11px] font-semibold text-amber-500 shadow-3d-floating backdrop-blur-xl transition-all hover:scale-105 hover:bg-card hover:border-amber-400"
          >
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-500 shadow-[0_0_8px_#f59e0b]" />
            </span>
            <span>{tx(`⚡ ${approvals.length} hành động cần xem lại →`, `⚡ ${approvals.length} action${approvals.length > 1 ? "s" : ""} need${approvals.length === 1 ? "s" : ""} review →`)}</span>
          </div>
        )}

        {/* Urgent Notification Counter Dot on Top-Right */}
        {approvals.length > 0 && (
          <div className="pointer-events-none absolute right-3 top-3 z-10 flex h-5 min-w-5 items-center justify-center rounded-full bg-amber-500 px-1.5 font-mono text-[10px] font-bold text-black shadow-[0_0_12px_rgba(245,158,11,0.8)] ring-2 ring-background">
            {approvals.length}
          </div>
        )}

        {/* 3D Model & Telemetry Holographic HUD Ring */}
        <div
          className={`relative h-full w-full transition-all duration-300 drop-shadow-[0_18px_28px_rgba(0,0,0,0.85)] ${
            isOpen ? "drop-shadow-[0_0_25px_rgba(59,130,246,0.4)]" : ""
          }`}
        >
          {/* Active Glow Ring when Opened */}
          {isOpen && (
            <div className="pointer-events-none absolute inset-2 rounded-full border border-primary/40 bg-primary/5 shadow-[inset_0_0_20px_rgba(59,130,246,0.2)] animate-pulse" />
          )}

          {/* Holographic Telemetry Rings */}
          <svg
            className="pointer-events-none absolute inset-[2%_4%_8%_4%] animate-spin-slow opacity-65"
            viewBox="0 0 200 200"
            fill="none"
            stroke="currentColor"
          >
            <circle
              cx="100"
              cy="100"
              r="94"
              stroke="currentColor"
              className="text-primary"
              strokeWidth="1"
              strokeDasharray="4 8"
              opacity="0.6"
            />
            <circle
              cx="100"
              cy="100"
              r="86"
              stroke="currentColor"
              className="text-primary"
              strokeWidth="1.5"
              strokeDasharray="24 16 8 16"
              opacity="0.8"
            />
            <circle
              cx="100"
              cy="100"
              r="76"
              stroke="currentColor"
              className="text-sky-400"
              strokeWidth="0.8"
              strokeDasharray="6 12"
              opacity="0.5"
            />
            <path
              d="M100 4 V16 M100 184 V196 M4 100 H16 M184 100 H196"
              stroke="currentColor"
              className="text-primary"
              strokeWidth="2"
            />
          </svg>

          {/* Cognition Metric Badge */}
          <div className="pointer-events-none absolute right-[8%] top-[8%] rounded-md border border-border/80 bg-card/90 px-1.5 py-0.5 font-mono text-[9px] font-medium text-primary shadow-sm backdrop-blur-md">
            {tx("SUY NGHĨ //", "COGNITION //")}{activeRoutinesCount}
          </div>

          {/* Holographic Pedestal Glow */}
          <div className="pointer-events-none absolute bottom-4 left-1/2 h-4 w-28 -translate-x-1/2 rounded-[100%] bg-primary/20 blur-md" />

          {/* Model Viewer Component */}
          <div className="h-full w-full">
            {/* @ts-ignore */}
            <model-viewer
              ref={modelViewerRef}
              src={config.modelUrl || "/agent-service-robot.glb"}
              alt={tx("Trợ lý 3D OpenAgent", "OpenAgent 3D Companion")}
              camera-orbit="0deg 75deg 2.2m"
              field-of-view="24deg"
              disable-zoom
              interaction-prompt="none"
              loading="eager"
              style={{ width: "100%", height: "100%", background: "transparent" }}
            />
          </div>
        </div>

        {/* Polished Companion Status Pill */}
        <div
          className={`pointer-events-none absolute -bottom-1 left-1/2 flex -translate-x-1/2 items-center gap-2 whitespace-nowrap rounded-full border px-3 py-1 text-xs shadow-card backdrop-blur-xl transition-all duration-200 ${
            isOpen
              ? "border-primary/80 bg-primary/15 text-foreground ring-2 ring-primary/30"
              : "border-border/90 bg-card/95 text-muted-foreground"
          }`}
        >
          <span
            className={`h-2 w-2 rounded-full ${
              approvals.length > 0
                ? "bg-amber-500 shadow-[0_0_8px_#f59e0b] animate-pulse"
                : "bg-emerald-500 shadow-[0_0_8px_#10b981]"
            }`}
          />
          <span className="font-semibold text-foreground">{config.name}</span>
          <span className="font-mono text-[10.5px] font-medium text-primary">
            {approvals.length > 0 ? `${approvals.length} pending` : "ready"}
          </span>
        </div>
      </div>

      {/* Floating Operator Command Surface */}
      <OperatorSurface
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        anchorRect={anchorRect}
        companionName={config.name}
        approvals={approvals}
        notifications={notifications}
        cases={cases}
        activeRoutinesCount={activeRoutinesCount}
        onDecideApproval={handleDecideApproval}
        onBatchDecideAllApprovals={handleBatchDecideAll}
        onSendDirection={handleSendDirection}
      />
    </>
  );
}
