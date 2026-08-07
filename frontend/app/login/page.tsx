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

  return <div className="mx-auto flex min-h-dvh max-w-md items-center px-4 py-12"><Card className="w-full border-border/80 shadow-3d-floating"><CardHeader className="space-y-3 pb-3 text-center"><div className="mx-auto grid h-12 w-12 place-items-center rounded-xl bg-primary text-primary-foreground shadow-card"><Bot className="h-6 w-6" aria-hidden="true" /></div><div><CardTitle className="text-xl">Welcome to OpenAgent</CardTitle><p className="mt-2 text-sm text-muted-foreground">Sign in to your multi-agent developer platform</p></div></CardHeader><CardContent><form onSubmit={submit} className="space-y-5"><div className="space-y-2"><Label htmlFor="login-email">Email</Label><Input id="login-email" type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="name@company.com" required /></div><div className="space-y-2"><Label htmlFor="login-password">Password</Label><Input id="login-password" type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required /></div><Button type="submit" className="h-11 w-full gap-2" loading={loading} disabled={!email || !password}>Sign in{!loading && <ArrowRight className="h-4 w-4" aria-hidden="true" />}</Button><p className="text-center text-sm text-muted-foreground">No account yet? <Link className="font-semibold text-primary underline-offset-4 hover:underline" href="/register">Create account</Link></p></form></CardContent></Card></div>;
}
