"use client";

import * as React from "react";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { Input, Label } from "@/components/ui/input";
import { Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useTranslation } from "@/lib/i18n";
import type { GraphNode } from "@/types";
import { NodeConfigForm } from "@/components/workflows/node-config-form";

interface WorkflowNodeConfigProps {
  node: GraphNode | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onUpdate: (patch: Partial<GraphNode>) => void;
  onDeleteNode?: (id: string) => void;
}

export function WorkflowNodeConfig({
  node,
  open,
  onOpenChange,
  onUpdate,
  onDeleteNode,
}: WorkflowNodeConfigProps) {
  const { t } = useTranslation();
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="bg-card/95 backdrop-blur-xl flex flex-col justify-between overflow-y-auto">
        <div>
          <SheetHeader>
            <SheetTitle>{t("pages.workflows.nodeConfigTitle", "Node configuration")}</SheetTitle>
            <SheetDescription>
              {node
                ? t("pages.workflows.nodeConfigEditing", 'Editing "{label}" ({kind})').replace("{label}", node.label || node.id).replace("{kind}", node.kind)
                : t("pages.workflows.nodeConfigTitle", "No node selected")}
            </SheetDescription>
          </SheetHeader>

        {node && (
          <div className="mt-6 space-y-4">
            <div className="space-y-1.5">
              <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/80">
                {t("pages.workflows.labelName", "Label name")}
              </Label>
              <Input
                className="text-xs"
                value={node.label}
                onChange={(e) => onUpdate({ label: e.target.value })}
                placeholder={t("pages.workflows.labelName", "Label name")}
              />
            </div>

            <NodeConfigForm node={node} onUpdate={onUpdate} />
          </div>
        )}
        </div>

        {node && onDeleteNode && (
          <div className="mt-8 border-t border-border/40 pt-4">
            <Button
              variant="outline"
              className="w-full gap-2 border-destructive/40 text-destructive hover:bg-destructive hover:text-destructive-foreground transition-all duration-150"
              onClick={() => {
                onDeleteNode(node.id);
                onOpenChange(false);
              }}
            >
              <Trash2 className="h-4 w-4" /> {t("pages.workflows.deleteNode", "Delete node")}
            </Button>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
