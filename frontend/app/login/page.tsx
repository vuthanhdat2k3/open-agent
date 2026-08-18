"use client";

import * as React from "react";
import Link from "next/link";
import { toast } from "sonner";
import { ArrowRight, Bot } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { setAccessToken } from "@/lib/auth";

export default function LoginPage() {
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [loading, setLoading] = React.useState(false);
  const zitadelEnabled = process.env.NEXT_PUBLIC_AUTH_PROVIDER === "zitadel";

  React.useEffect(() => {
    if (window.location.hostname === "localhost") {
      const canonical = new URL(window.location.href);
      canonical.hostname = "127.0.0.1.sslip.io";
      window.location.replace(canonical.toString());
    }
  }, []);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    try {
      const response = await fetch("/api/auth/login", { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, password }) });
      if (!response.ok) throw new Error("Invalid email or password");
      const data = (await response.json()) as { access_token: string };
      setAccessToken(data.access_token);
      window.location.replace("/");
    } catch (error: unknown) {
      toast.error(error instanceof Error ? error.message : "Unable to sign in");
    } finally { setLoading(false); }
  }

  if (zitadelEnabled) {
    return <div className="mx-auto flex min-h-dvh max-w-md items-center px-4 py-12"><Card className="w-full border-border/80 shadow-3d-floating"><CardHeader className="space-y-3 pb-3 text-center"><div className="mx-auto grid h-12 w-12 place-items-center rounded-xl bg-primary text-primary-foreground shadow-card"><Bot className="h-6 w-6" aria-hidden="true" /></div><div><CardTitle className="text-xl">Sign in to OpenAgent</CardTitle><p className="mt-2 text-sm text-muted-foreground">Authentication is managed by your organization identity provider.</p></div></CardHeader><CardContent><Button type="button" className="h-11 w-full gap-2" onClick={() => { window.location.href = "/api/auth/login"; }}>Continue with organization SSO<ArrowRight className="h-4 w-4" aria-hidden="true" /></Button></CardContent></Card></div>;
  }

  return <div className="mx-auto flex min-h-dvh max-w-md items-center px-4 py-12"><Card className="w-full border-border/80 shadow-3d-floating"><CardHeader className="space-y-3 pb-3 text-center"><div className="mx-auto grid h-12 w-12 place-items-center rounded-xl bg-primary text-primary-foreground shadow-card"><Bot className="h-6 w-6" aria-hidden="true" /></div><div><CardTitle className="text-xl">Local authentication is disabled</CardTitle><p className="mt-2 text-sm text-muted-foreground">Use the configured organization identity provider to sign in.</p></div></CardHeader></Card></div>;
}
