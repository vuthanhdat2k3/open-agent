"use client";

import * as React from "react";
import { Terminal, CheckCircle2, AlertCircle, Play, Pause, Copy, Check, Clock, ShieldAlert, GitCommit } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";

export type WorkflowLogItem = {
  id: string;
  ts: number;
  event: string;
  node_id?: string;
  message: string;
  output?: string;
};

interface WorkflowConsoleProps {
  logs: WorkflowLogItem[];
  output: string;
  running: boolean;
}

export function WorkflowConsole({ logs, output, running }: WorkflowConsoleProps) {
  const [activeTab, setActiveTab] = React.useState<"logs" | "output">("logs");
  const [copied, setCopied] = React.useState(false);
  const logEndRef = React.useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom whenever new logs arrive
  React.useEffect(() => {
    if (activeTab === "logs") {
      logEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs.length, activeTab]);

  // Switch to output tab automatically when workflow completes and has output
  React.useEffect(() => {
    if (output && !running) {
      // keep current tab or let user switch freely
    }
  }, [output, running]);

  const copyOutput = () => {
    if (!output) return;
    navigator.clipboard.writeText(output);
    setCopied(true);
    toast.success("Output copied to clipboard");
    setTimeout(() => setCopied(false), 2000);
  };

  const getEventBadge = (event: string) => {
    switch (event) {
      case "node_start":
        return <Badge variant="outline" className="border-info/40 text-info bg-info/10 text-[9px] py-0 font-mono">START</Badge>;
      case "node_done":
        return <Badge variant="outline" className="border-success/40 text-success bg-success/10 text-[9px] py-0 font-mono">DONE</Badge>;
      case "node_error":
      case "error":
        return <Badge variant="outline" className="border-destructive/40 text-destructive bg-destructive/10 text-[9px] py-0 font-mono">ERROR</Badge>;
      case "approval_required":
        return <Badge variant="outline" className="border-warning/40 text-warning bg-warning/10 text-[9px] py-0 font-mono">WAIT</Badge>;
      case "edge":
        return <Badge variant="outline" className="border-border text-muted-foreground text-[9px] py-0 font-mono">EDGE</Badge>;
      case "done":
        return <Badge variant="outline" className="border-primary/40 text-primary bg-primary/10 text-[9px] py-0 font-mono font-bold">FINISH</Badge>;
      default:
        return <Badge variant="outline" className="text-[9px] py-0 font-mono">{event}</Badge>;
    }
  };

  const getEventTextColor = (event: string) => {
    switch (event) {
      case "node_error":
      case "error":
        return "text-destructive font-semibold";
      case "node_done":
      case "done":
        return "text-success font-medium";
      case "node_start":
        return "text-info";
      case "approval_required":
        return "text-warning font-semibold";
      case "edge":
        return "text-muted-foreground/80";
      default:
        return "text-foreground";
    }
  };

  return (
    <Card glass className="overflow-hidden shadow-3d-card border-border/80">
      <CardHeader className="flex flex-row items-center justify-between border-b border-border/60 bg-muted/20 px-4 py-2.5">
        <div className="flex items-center gap-3">
          <div className="grid h-8 w-8 place-items-center rounded-xl bg-gradient-to-br from-primary/25 via-primary/10 to-transparent text-primary shadow-3d-card border border-primary/20">
            <Terminal className="h-4 w-4" />
          </div>
          <div>
            <CardTitle className="text-sm font-semibold tracking-tight text-foreground">Workflow Run Console</CardTitle>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Navigation Tabs */}
          <div className="flex rounded-lg bg-muted/50 p-1 border border-border/40 text-xs font-medium">
            <button
              onClick={() => setActiveTab("logs")}
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md transition-all ${
                activeTab === "logs"
                  ? "bg-card text-foreground shadow-inner-edge font-semibold"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <Clock className="h-3 w-3" />
              Live Logs
              {logs.length > 0 && (
                <span className="ml-1 rounded-full bg-primary/20 text-primary px-1.5 py-0.2 text-[10px] font-mono font-bold">
                  {logs.length}
                </span>
              )}
            </button>
            <button
              onClick={() => setActiveTab("output")}
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md transition-all ${
                activeTab === "output"
                  ? "bg-card text-foreground shadow-inner-edge font-semibold"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <CheckCircle2 className="h-3 w-3" />
              Final Output
            </button>
          </div>

          {activeTab === "output" && output && (
            <Button size="sm" variant="outline" className="h-7 gap-1 text-[11px] active-tactile transition-transform" onClick={copyOutput}>
              {copied ? <Check className="h-3 w-3 text-success" /> : <Copy className="h-3 w-3" />}
              {copied ? "Copied" : "Copy"}
            </Button>
          )}
        </div>
      </CardHeader>

      <CardContent className="p-0 bg-black/40 font-mono text-[11px] select-text">
        {activeTab === "logs" ? (
          <div className="max-h-80 overflow-auto p-3 space-y-1.5 scrollbar-thin">
            {logs.length > 0 ? (
              logs.map((item) => {
                const dateStr = new Date(item.ts).toLocaleTimeString("en-US", {
                  hour12: false,
                  hour: "2-digit",
                  minute: "2-digit",
                  second: "2-digit",
                });
                return (
                  <div key={item.id} className="flex items-start gap-2 py-0.5 border-b border-border/10 last:border-0 hover:bg-white/5 px-1.5 rounded transition-colors">
                    <span className="text-[10px] text-muted-foreground/60 shrink-0 mt-0.5">{dateStr}</span>
                    <span className="shrink-0 mt-0.5">{getEventBadge(item.event)}</span>
                    {item.node_id && (
                      <span className="text-[10px] bg-muted/30 border border-border/30 text-muted-foreground px-1.5 py-0.2 rounded font-mono shrink-0 mt-0.5">
                        {item.node_id}
                      </span>
                    )}
                    <span className={`break-all leading-relaxed ${getEventTextColor(item.event)}`}>
                      {item.message}
                    </span>
                  </div>
                );
              })
            ) : (
              <div className="py-12 text-center text-muted-foreground/60 text-xs font-sans">
                {running ? (
                  <span className="flex items-center justify-center gap-2 text-info">
                    <span className="h-2 w-2 rounded-full bg-info animate-ping" />
                    Executing workflow and streaming live events…
                  </span>
                ) : (
                  "No execution logs yet. Run workflow to stream real-time events."
                )}
              </div>
            )}
            <div ref={logEndRef} />
          </div>
        ) : (
          <pre className="max-h-80 overflow-auto whitespace-pre-wrap p-4 text-foreground leading-relaxed scrollbar-thin">
            {output || "Console waiting for workflow execution output…"}
          </pre>
        )}
      </CardContent>
    </Card>
  );
}
