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
} from "@/hooks";
import type { EvaluationSuite } from "@/types";
import { PageHeader } from "@/components/page-header";
import { EmptyState } from "@/components/empty-state";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input, Label, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
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
  const [selectedSuiteId, setSelectedSuiteId] = React.useState<string | null>(null);
  const runs = useEvaluationRuns(selectedSuiteId);
  const [form, setForm] = React.useState(EMPTY_SUITE);
  const [caseForm, setCaseForm] = React.useState({ input: "", expected_output: "" });

  React.useEffect(() => {
    if (!selectedSuiteId && suites.data?.length) {
      setSelectedSuiteId(suites.data[0].id);
    }
  }, [selectedSuiteId, suites.data]);

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
        description="Versioned test suites and release quality gates"
        actions={
          <Button className="gap-2" onClick={() => setSuiteDialog(true)}>
            <Plus className="h-4 w-4" /> New Suite
          </Button>
        }
      />

      {suites.isLoading ? (
        <div className="space-y-3">
          <Skeleton className="h-32 w-full" />
          <Skeleton className="h-32 w-full" />
        </div>
      ) : suites.data?.length ? (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
          <div className="space-y-3">
            {suites.data.map((suite) => {
              const agent = agents.data?.find((item) => item.id === suite.agent_id);
              return (
                <section
                  key={suite.id}
                  className="border-b border-border/60 pb-5"
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <div className="flex items-center gap-2">
                        <h2 className="text-sm font-semibold">{suite.name}</h2>
                        <Badge variant="outline">dataset v{suite.dataset_version}</Badge>
                      </div>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {suite.description || "No description"} | {agent?.name ?? "Unknown agent"}
                      </p>
                    </div>
                    <div className="flex gap-1.5">
                      <Button
                        size="sm"
                        variant="outline"
                        className="gap-1.5"
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
                        className="gap-1.5"
                        onClick={() => runSuite(suite, "recorded")}
                        disabled={createRun.isPending || !suite.cases.length}
                      >
                        <Database className="h-3.5 w-3.5" /> Baseline
                      </Button>
                      <Button
                        size="sm"
                        className="gap-1.5"
                        onClick={() => runSuite(suite, "live")}
                        disabled={createRun.isPending || !suite.cases.length}
                      >
                        <Play className="h-3.5 w-3.5" /> Live
                      </Button>
                    </div>
                  </div>
                  <div className="mt-3 overflow-hidden rounded-md border border-border/50">
                    {suite.cases.map((testCase) => (
                      <button
                        key={testCase.id}
                        className="grid w-full grid-cols-[44px_minmax(0,1fr)_100px] items-center gap-3 border-b border-border/40 px-3 py-2 text-left text-xs last:border-0 hover:bg-muted/30"
                        onClick={() => setSelectedSuiteId(suite.id)}
                      >
                        <span className="font-mono text-muted-foreground">
                          #{testCase.ordinal}
                        </span>
                        <span className="truncate">{testCase.input}</span>
                        <span className="text-right text-[10px] text-muted-foreground">
                          added v{testCase.added_in_version}
                        </span>
                      </button>
                    ))}
                    {!suite.cases.length && (
                      <p className="px-3 py-4 text-xs text-muted-foreground">
                        No test cases.
                      </p>
                    )}
                  </div>
                </section>
              );
            })}
          </div>

          <aside className="border-l border-border/60 pl-5">
            <h2 className="text-xs font-semibold uppercase text-muted-foreground">
              Recent runs
            </h2>
            <div className="mt-3 space-y-2">
              {runs.data?.map((run) => (
                <div
                  key={run.id}
                  className="border-b border-border/50 py-3 first:pt-0"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      {run.pass_rate === 1 ? (
                        <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                      ) : (
                        <XCircle className="h-4 w-4 text-destructive" />
                      )}
                      <span className="font-mono text-sm">
                        {(run.pass_rate * 100).toFixed(0)}%
                      </span>
                    </div>
                    <Badge variant="outline">{run.execution_mode}</Badge>
                  </div>
                  <p className="mt-1 text-[10px] text-muted-foreground">
                    {run.passed_cases}/{run.total_cases} cases |{" "}
                    {run.average_latency_ms.toFixed(0)} ms | $
                    {run.total_cost_usd.toFixed(4)}
                  </p>
                </div>
              ))}
              {!runs.data?.length && (
                <p className="text-xs text-muted-foreground">No runs yet.</p>
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
            <Button className="gap-2" onClick={() => setSuiteDialog(true)}>
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
          <div className="space-y-4">
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
              className="w-full"
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
          <div className="space-y-4">
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
              className="w-full"
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
