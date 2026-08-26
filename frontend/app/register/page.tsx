"use client";

import * as React from "react";
import Link from "next/link";
import { toast } from "sonner";
import { ArrowRight, Bot } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { setAccessToken } from "@/lib/auth";
import { useTranslation } from "@/lib/i18n";

export default function RegisterPage() {
    const { locale } = useTranslation();
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [orgName, setOrgName] = React.useState("");
  const [loading, setLoading] = React.useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    try {
      const response = await fetch("/api/auth/register", { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, password, org_name: orgName || undefined }) });
      if (!response.ok) throw new Error("Registration failed");
      const data = (await response.json()) as { access_token: string };
      setAccessToken(data.access_token);
      window.location.href = "/";
    } catch (error: unknown) {
      toast.error(error instanceof Error ? error.message : "Unable to create account");
    } finally { setLoading(false); }
  }

  return <div className="mx-auto flex min-h-dvh max-w-md items-center px-4 py-12"><Card className="w-full border-border/80 shadow-3d-floating"><CardHeader className="space-y-3 pb-3 text-center"><div className="mx-auto grid h-12 w-12 place-items-center rounded-xl bg-primary text-primary-foreground shadow-card"><Bot className="h-6 w-6" aria-hidden="true" /></div><div><CardTitle className="text-xl">{locale === "vi" ? "Create your account" : "Create your account"}</CardTitle><p className="mt-2 text-sm text-muted-foreground">{locale === "vi" ? "Start building multi-agent AI systems with OpenAgent" : "Start building multi-agent AI systems with OpenAgent"}</p></div></CardHeader><CardContent><form onSubmit={submit} className="space-y-5"><div className="space-y-2"><Label htmlFor="register-email">{locale === "vi" ? "Email" : "Email"}</Label><Input id="register-email" type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder={locale === "vi" ? "name@company.com" : "name@company.com"} required /></div><div className="space-y-2"><Label htmlFor="register-password">{locale === "vi" ? "Mật khẩu" : "Password"}</Label><Input id="register-password" type="password" autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} required minLength={6} /></div><div className="space-y-2"><Label htmlFor="register-org">{locale === "vi" ? "Organization (optional)" : "Organization (optional)"}</Label><Input id="register-org" value={orgName} onChange={(event) => setOrgName(event.target.value)} placeholder={locale === "vi" ? "Acme Inc." : "Acme Inc."} /></div><Button type="submit" className="h-11 w-full gap-2" loading={loading} disabled={!email || !password}>{locale === "vi" ? "Create account" : "Create account"}{!loading && <ArrowRight className="h-4 w-4" aria-hidden="true" />}</Button><p className="text-center text-sm text-muted-foreground">{locale === "vi" ? "Already have an account?" : "Already have an account?"}<Link className="font-semibold text-primary underline-offset-4 hover:underline" href="/login">{locale === "vi" ? "Sign in" : "Sign in"}</Link></p></form></CardContent></Card></div>;
}
