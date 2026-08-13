"use client";

import * as React from "react";
import { Bell, Check, MailOpen, ShieldAlert } from "lucide-react";
import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { PageHeader } from "@/components/page-header";
import { EmptyState, ErrorState, LoadingSkeleton } from "@/components/shared";
import { useCustomerIntelligenceNotifications, useMarkCustomerIntelligenceNotificationRead } from "@/hooks";

function notificationVariant(type: string) {
  if (type.includes("security") || type.includes("quarantine")) return "destructive" as const;
  if (type.includes("calendar") || type.includes("customer")) return "info" as const;
  return "outline" as const;
}

export default function EmailIntelligencePage() {
  const [unreadOnly, setUnreadOnly] = React.useState(false);
  const notifications = useCustomerIntelligenceNotifications(unreadOnly);
  const markRead = useMarkCustomerIntelligenceNotificationRead();

  return (
    <div className="space-y-6">
      <PageHeader icon={Bell} title="Smart Inbox" description="Email routing, notifications and safe next steps for your connected accounts." />
      <div className="flex flex-wrap items-center gap-2" role="tablist" aria-label="Inbox filters">
        <Button variant={!unreadOnly ? "default" : "outline"} size="sm" onClick={() => setUnreadOnly(false)} role="tab" aria-selected={!unreadOnly}>All notifications</Button>
        <Button variant={unreadOnly ? "default" : "outline"} size="sm" onClick={() => setUnreadOnly(true)} role="tab" aria-selected={unreadOnly}>Unread only</Button>
      </div>
      {notifications.isLoading ? <LoadingSkeleton variant="table" /> : notifications.isError ? <ErrorState title="Unable to load inbox" description="Notifications could not be loaded." onRetry={() => void notifications.refetch()} /> : notifications.data?.length ? (
        <div className="space-y-3" aria-live="polite">
          {notifications.data.map((item) => (
            <Card key={item.id} className={item.read_at ? "opacity-75" : "border-primary/40"}>
              <CardContent className="flex items-start gap-4 p-5">
                <div className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-primary/10 text-primary">
                  {item.type.includes("security") ? <ShieldAlert className="h-4 w-4" aria-hidden="true" /> : <Bell className="h-4 w-4" aria-hidden="true" />}
                </div>
                <div className="min-w-0 flex-1 space-y-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="font-semibold">{item.title}</h2>
                    <Badge variant={notificationVariant(item.type)}>{item.type}</Badge>
                    {!item.read_at && <Badge variant="success">Unread</Badge>}
                  </div>
                  <p className="text-sm text-muted-foreground">{item.body}</p>
                  <p className="text-xs text-muted-foreground">{new Date(item.created_at).toLocaleString()}</p>
                  <div className="flex flex-wrap gap-2 pt-1">
                    <Link href={`/customer-intelligence?email_id=${encodeURIComponent(item.email_id)}`} className="text-sm font-medium text-primary hover:underline">Open related research</Link>
                    {!item.read_at && <Button size="sm" variant="outline" onClick={() => markRead.mutate(item.id)} disabled={markRead.isPending}><Check className="mr-1 h-3.5 w-3.5" />Mark read</Button>}
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : <Card><CardHeader><CardTitle className="flex items-center gap-2"><MailOpen className="h-5 w-5" />Inbox clear</CardTitle><CardDescription>No notifications match the selected filter.</CardDescription></CardHeader><CardContent><EmptyState icon={Bell} title="No email notifications" description="Connect Gmail to receive routed email summaries and customer research updates." /></CardContent></Card>}
    </div>
  );
}
