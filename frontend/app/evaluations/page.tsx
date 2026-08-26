"use client";

import * as React from "react";
import { FlaskConical, Plus, Play, Database, CheckCircle2, XCircle } from "lucide-react";
import { toast } from "sonner";
import {
  useAddEvaluationCase,
  useAgents,
  useCreateEvaluationRun,
  useCreateEvaluationSuite,
  useEvaluationRuns,
  useEvaluationSuites,
  useUrlSearchParam,
} from "@/hooks";
import type { EvaluationSuite } from "@/types";
import { PageHeader } from "@/components/page-header";
import { EmptyState, ErrorState, LoadingSkeleton, DataPagination } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input, Label, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Card } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

const EMPTY_SUITE = {
  name: "",
  description: "",
  agent_id: "",
  input: "",
  expected_output: "",
};

export default function EvaluationsPage() {
  const suites = useEvaluationSuites();
  const agents = useAgents();
  const createSuite = useCreateEvaluationSuite();
  const addCase = useAddEvaluationCase();
  const createRun = useCreateEvaluationRun();
  const [suiteDialog, setSuiteDialog] = React.useState(false);
  const [caseSuite, setCaseSuite] = React.useState<EvaluationSuite | null>(null);
  const [selectedSuiteId, setSelectedSuiteId] = useUrlSearchParam("suite");
  const runs = useEvaluationRuns(selectedSuiteId);
  const [form, setForm] = React.useState(EMPTY_SUITE);
  const [caseForm, setCaseForm] = React.useState({ input: "", expected_output: "" });
  const [suitePage, setSuitePage] = React.useState(1);
  const [suitePageSize, setSuitePageSize] = React.useState(5);

  const paginatedSuites = React.useMemo(() => {
    const start = (suitePage - 1) * suitePageSize;
    return (suites.data || []).slice(start, start + suitePageSize);
  }, [suites.data, suitePage, suitePageSize]);

  React.useEffect(() => {
    if (!selectedSuiteId && suites.data?.length) {
      setSelectedSuiteId(suites.data[0].id);
    }
  }, [selectedSuiteId, setSelectedSuiteId, suites.data]);

  React.useEffect(() => {
    if (!form.agent_id && agents.data?.length) {
      setForm((current) => ({ ...current, agent_id: agents.data![0].id }));
    }
  }, [agents.data, form.agent_id]);

  const submitSuite = async () => {
    try {
      const created = await createSuite.mutateAsync({
        name: form.name,
        description: form.description,
        agent_id: form.agent_id,
        cases: form.input
          ? [{ input: form.input, expected_output: form.expected_output || null }]
          : [],
      });
      setSuiteDialog(false);
      setSelectedSuiteId(created.id);
      setForm({ ...EMPTY_SUITE, agent_id: form.agent_id });
      toast.success("Evaluation suite created");
    } catch (error: any) {
      toast.error(error.message);
    }
  };

  const submitCase = async () => {
    if (!caseSuite) return;
    try {
      await addCase.mutateAsync({
        suiteId: caseSuite.id,
        input: caseForm.input,
        expected_output: caseForm.expected_output || null,
      });
      setCaseSuite(null);
      setCaseForm({ input: "", expected_output: "" });
      toast.success("Test case added");
    } catch (error: any) {
      toast.error(error.message);
    }
  };

  const runSuite = async (suite: EvaluationSuite, mode: "live" | "recorded") => {
    const agent = agents.data?.find((item) => item.id === suite.agent_id);
    if (!agent?.active_release_id) {
      toast.error("Agent has no active release");
      return;
    }
    try {
      const recorded_outputs =
        mode === "recorded"
          ? suite.cases.map((testCase) => ({
              case_id: testCase.id,
              output:
                testCase.expected_output ??
                testCase.required_substrings.join(" "),
              observed_tools: testCase.expected_tools,
              latency_ms: 0,
              cost_usd: 0,
            }))
          : [];
      const run = await createRun.mutateAsync({
        suiteId: suite.id,
        agent_release_id: agent.active_release_id,
        execution_mode: mode,
        recorded_outputs,
      });
      setSelectedSuiteId(suite.id);
      toast.success(
        `Evaluation complete: ${(run.pass_rate * 100).toFixed(0)}% passed`
      );
    } catch (error: any) {
      toast.error(error.message);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        icon={FlaskConical}
        title="Evaluations"
        description="Run benchmark test suites, track pass rates, and verify model quality."
        actions={
          <Button className="gap-2 active-tactile transition-transform" onClick={() => setSuiteDialog(true)}>
            <Plus className="h-4 w-4" /> New Suite
          </Button>
        }
      />

      {suites.isLoading ? <LoadingSkeleton variant="table" /> : suites.isError ? <ErrorState title="Unable to load evaluation suites" description="Evaluation data could not be loaded." onRetry={() => void suites.refetch()} /> : suites.data?.length ? (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px] stagger">
          <div className="space-y-4">
            {paginatedSuites.map((suite) => {
              const agent = agents.data?.find((item) => item.id === suite.agent_id);
              return (
                <Card
                  key={suite.id}
                  glass
                  className="card-lift p-5 space-y-4 overflow-hidden"
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <div className="flex items-center gap-2">
                        <h2 className="text-base font-semibold tracking-tight text-foreground">{suite.name}</h2>
                        <Badge variant="outline" className="font-mono text-[10px]">v{suite.dataset_version}</Badge>
                      </div>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {suite.description || "No description"} · <span className="font-medium text-foreground">{agent?.name ?? "Unknown agent"}</span>
                      </p>
                    </div>
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        className="gap-1.5 active-tactile transition-transform text-xs"
                        onClick={() => {
                          setCaseSuite(suite);
                          setSelectedSuiteId(suite.id);
                        }}
                      >
                        <Plus className="h-3.5 w-3.5" /> Case
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        className="gap-1.5 active-tactile transition-transform text-xs"
                        onClick={() => runSuite(suite, "recorded")}
                        disabled={createRun.isPending || !suite.cases.length}
                      >
                        <Database className="h-3.5 w-3.5" /> Baseline
                      </Button>
                      <Button
                        size="sm"
                        className="gap-1.5 active-tactile transition-transform text-xs"
                        onClick={() => runSuite(suite, "live")}
                        disabled={createRun.isPending || !suite.cases.length}
                      >
                        <Play className="h-3.5 w-3.5" /> Live
                      </Button>
                    </div>
                  </div>
                  <div className="overflow-hidden rounded-xl border border-border/60 bg-muted/20">
                    {suite.cases.map((testCase) => (
                      <button
                        key={testCase.id}
                        className="grid w-full grid-cols-[44px_minmax(0,1fr)_100px] items-center gap-3 border-b border-border/40 px-3.5 py-2.5 text-left text-xs last:border-0 hover:bg-accent/40 transition-colors"
                        onClick={() => setSelectedSuiteId(suite.id)}
                      >
                        <span className="font-mono text-muted-foreground text-[11px]">
                          #{testCase.ordinal}
                        </span>
                        <span className="truncate text-foreground font-medium">{testCase.input}</span>
                        <span className="text-right text-[10px] font-mono text-muted-foreground">
                          v{testCase.added_in_version}
                        </span>
                      </button>
                    ))}
                    {!suite.cases.length && (
                      <p className="px-4 py-4 text-xs text-muted-foreground text-center">
                        No test cases.
                      </p>
                    )}
                  </div>
                </Card>
              );
            })}
            <DataPagination
              page={suitePage}
              pageSize={suitePageSize}
              totalItems={suites.data.length}
              onPageChange={setSuitePage}
              onPageSizeChange={setSuitePageSize}
              pageSizeOptions={[3, 5, 10, 20]}
            />
          </div>

          <aside className="rounded-xl border border-border/80 bg-card/45 p-5 space-y-4 backdrop-blur-xl shadow-3d-card">
            <h2 className="text-xs font-bold uppercase tracking-wider text-muted-foreground/80">
              Recent runs
            </h2>
            <div className="space-y-3">
              {runs.data?.map((run) => (
                <div
                  key={run.id}
                  className="rounded-lg border border-border/40 bg-muted/20 p-3 space-y-1.5 shadow-inner-edge"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      {run.pass_rate === 1 ? (
                        <CheckCircle2 className="h-4 w-4 text-success" />
                      ) : (
                        <XCircle className="h-4 w-4 text-destructive" />
                      )}
                      <span className="font-mono text-sm font-bold text-foreground">
                        {(run.pass_rate * 100).toFixed(0)}%
                      </span>
                    </div>
                    <Badge variant="outline" className="font-mono text-[10px]">{run.execution_mode}</Badge>
                  </div>
                  <p className="text-[11px] font-mono text-muted-foreground">
                    {run.passed_cases}/{run.total_cases} cases · {run.average_latency_ms.toFixed(0)}ms · ${run.total_cost_usd.toFixed(4)}
                  </p>
                </div>
              ))}
              {!runs.data?.length && (
                <p className="text-xs text-muted-foreground/80 py-4 text-center">No runs recorded.</p>
              )}
            </div>
          </aside>
        </div>
      ) : (
        <EmptyState
          icon={FlaskConical}
          title="No evaluation suites"
          description="Create a repeatable quality gate for an agent release."
          action={
            <Button className="gap-2 active-tactile transition-transform" onClick={() => setSuiteDialog(true)}>
              <Plus className="h-4 w-4" /> New Suite
            </Button>
          }
        />
      )}

      <Dialog open={suiteDialog} onOpenChange={setSuiteDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>New evaluation suite</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 pt-1">
            <div className="space-y-1.5">
              <Label>Name</Label>
              <Input
                value={form.name}
                onChange={(event) => setForm({ ...form, name: event.target.value })}
              />
            </div>
            <div className="space-y-1.5">
              <Label>Agent</Label>
              <Select
                value={form.agent_id}
                onChange={(event) =>
                  setForm({ ...form, agent_id: event.target.value })
                }
              >
                {agents.data?.map((agent) => (
                  <option key={agent.id} value={agent.id}>
                    {agent.name} | v{agent.latest_release_number}
                  </option>
                ))}
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Description</Label>
              <Input
                value={form.description}
                onChange={(event) =>
                  setForm({ ...form, description: event.target.value })
                }
              />
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label>First input</Label>
                <Textarea
                  value={form.input}
                  onChange={(event) => setForm({ ...form, input: event.target.value })}
                />
              </div>
              <div className="space-y-1.5">
                <Label>Expected output</Label>
                <Textarea
                  value={form.expected_output}
                  onChange={(event) =>
                    setForm({ ...form, expected_output: event.target.value })
                  }
                />
              </div>
            </div>
            <Button
              className="w-full active-tactile transition-transform"
              onClick={submitSuite}
              disabled={createSuite.isPending || !form.name || !form.agent_id}
            >
              {createSuite.isPending ? "Creating..." : "Create suite"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={!!caseSuite} onOpenChange={(value) => !value && setCaseSuite(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add case to {caseSuite?.name}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 pt-1">
            <div className="space-y-1.5">
              <Label>Input</Label>
              <Textarea
                value={caseForm.input}
                onChange={(event) =>
                  setCaseForm({ ...caseForm, input: event.target.value })
                }
              />
            </div>
            <div className="space-y-1.5">
              <Label>Expected output</Label>
              <Textarea
                value={caseForm.expected_output}
                onChange={(event) =>
                  setCaseForm({ ...caseForm, expected_output: event.target.value })
                }
              />
            </div>
            <Button
              className="w-full active-tactile transition-transform"
              onClick={submitCase}
              disabled={addCase.isPending || !caseForm.input}
            >
              {addCase.isPending ? "Adding..." : "Add case"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
