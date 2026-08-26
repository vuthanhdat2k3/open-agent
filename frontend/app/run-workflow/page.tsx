"use client";

import * as React from "react";
import { CheckCircle2, Play, Workflow as WorkflowIcon } from "lucide-react";
import { toast } from "sonner";
import { useWorkflowRun, useWorkflows } from "@/hooks";
import { streamSSE } from "@/lib/api";
import { PageHeader } from "@/components/page-header";
import { useTranslation } from "@/lib/i18n";
import { EmptyState, ErrorState, LoadingSkeleton } from "@/components/shared";
import { WorkflowConsole, type WorkflowLogItem } from "@/components/workflows/workflow-console";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Label, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/select";

const TERMINAL_STATUSES = new Set([
  "succeeded",
  "failed",
  "diverged",
  "cancelled",
  "waiting_approval",
]);

export default function RunWorkflowPage() {
  const { t, dict, locale } = useTranslation();
  const workflows = useWorkflows();
  const [workflowId, setWorkflowId] = React.useState("");
  const [input, setInput] = React.useState("");
  const [activeRunId, setActiveRunId] = React.useState<string | null>(null);
  const [starting, setStarting] = React.useState(false);
  const workflowRun = useWorkflowRun(activeRunId);
  const notifiedRun = React.useRef<string | null>(null);

  React.useEffect(() => {
    if (!workflowId && workflows.data?.length) {
      setWorkflowId(workflows.data[0].id);
    }
  }, [workflowId, workflows.data]);

  const status = workflowRun.data?.status;
  const running = starting || Boolean(activeRunId && (!status || !TERMINAL_STATUSES.has(status)));
  const output = String(workflowRun.data?.output?.text ?? "");
  const selectedWorkflow = workflows.data?.find((workflow) => workflow.id === workflowId);

  const logs = React.useMemo<WorkflowLogItem[]>(
    () =>
      (workflowRun.data?.nodes ?? []).map((node) => ({
        id: node.id,
        ts: new Date(node.started_at).getTime(),
        event:
          node.status === "succeeded"
            ? "node_done"
            : node.status === "failed"
              ? "node_error"
              : "node_start",
        node_id: node.node_id,
        message: `Node "${node.node_id}" ${node.status}`,
        output: typeof node.output?.text === "string" ? node.output.text : undefined,
      })),
    [workflowRun.data?.nodes],
  );

  React.useEffect(() => {
    if (!activeRunId || !status || !TERMINAL_STATUSES.has(status)) return;
    if (notifiedRun.current === activeRunId) return;
    notifiedRun.current = activeRunId;
    if (status === "succeeded") toast.success("Workflow completed");
    else if (status === "waiting_approval") toast.info("Workflow is waiting for approval");
    else toast.error(workflowRun.data?.error || `Workflow ${status}`);
  }, [activeRunId, status, workflowRun.data?.error]);

  async function run(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workflowId || !input.trim()) return;
    setStarting(true);
    setActiveRunId(null);
    let runId: string | null = null;
    try {
      await streamSSE(
        `/api/workflows/${workflowId}/run`,
        { input: input.trim(), stream: true, timezone: Intl.DateTimeFormat().resolvedOptions().timeZone },
        (streamEvent) => {
          if (streamEvent.event === "workflow_start") {
            runId = streamEvent.data.workflow_run_id;
          }
        },
      );
      if (!runId) throw new Error("Workflow did not return a run id");
      setActiveRunId(runId);
    } catch (error: any) {
      toast.error(error.message || "Unable to start workflow");
    } finally {
      setStarting(false);
    }
  }

  return (
    <div className="space-y-8">
      <PageHeader
        icon={WorkflowIcon}
        title={dict.pages.runWorkflow.title}
        description={dict.pages.runWorkflow.description}
      />

      {workflows.isLoading ? (
        <LoadingSkeleton variant="page" />
      ) : workflows.isError ? (
        <ErrorState
          title="Unable to load workflows"
          description="Available workflows could not be loaded."
          onRetry={() => void workflows.refetch()}
        />
      ) : !workflows.data?.length ? (
        <EmptyState
          icon={WorkflowIcon}
          title="No workflows available"
          description="Ask an administrator to prepare a workflow before trying to run one."
        />
      ) : (
        <Card glass className="shadow-3d-card">
          <CardContent className="p-6">
            <form className="space-y-5" onSubmit={run} aria-busy={running}>
              <div className="grid gap-5 lg:grid-cols-[minmax(240px,0.7fr)_minmax(0,1.3fr)]">
                <div className="space-y-2">
                  <Label htmlFor="workflow-select">Workflow</Label>
                  <Select
                    id="workflow-select"
                    value={workflowId}
                    onChange={(event) => {
                      setWorkflowId(event.target.value);
                      setActiveRunId(null);
                    }}
                  >
                    {workflows.data?.map((workflow) => (
                      <option key={workflow.id} value={workflow.id}>
                        {workflow.name}
                      </option>
                    ))}
                  </Select>
                  <p className="text-sm leading-relaxed text-muted-foreground">
                    {selectedWorkflow?.description || "This workflow is ready to run."}
                  </p>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="workflow-input">Input</Label>
                  <Textarea
                    id="workflow-input"
                    value={input}
                    onChange={(event) => setInput(event.target.value)}
                    placeholder="Describe what you want this workflow to process..."
                    className="min-h-32 resize-y"
                    required
                  />
                </div>
              </div>

              <div className="flex flex-col gap-3 border-t border-border/60 pt-5 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex items-center gap-2 text-sm text-muted-foreground" aria-live="polite">
                  {status && (
                    <>
                      <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
                      <span>Latest run</span>
                      <Badge variant={status === "succeeded" ? "success" : status === "failed" ? "destructive" : "outline"}>
                        {status}
                      </Badge>
                    </>
                  )}
                </div>
                <Button
                  type="submit"
                  className="min-h-11 gap-2 sm:min-w-40"
                  loading={starting}
                  disabled={running || !workflowId || !input.trim()}
                >
                  <Play className="h-4 w-4" aria-hidden="true" />
                  {running ? "Running..." : "Run Workflow"}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      <WorkflowConsole logs={logs} output={output} running={running} />
    </div>
  );
}
