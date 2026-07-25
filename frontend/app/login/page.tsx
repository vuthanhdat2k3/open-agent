"use client";

import * as React from "react";
import Link from "next/link";
import { toast } from "sonner";
import { Bot, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { setAccessToken } from "@/lib/auth";

export default function LoginPage() {
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [loading, setLoading] = React.useState(false);

  async function submit() {
    setLoading(true);
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      if (!res.ok) throw new Error("Invalid email or password");
      const data = (await res.json()) as { access_token: string };
      setAccessToken(data.access_token);
      window.location.replace("/");
    } catch (error: any) {
      toast.error(error.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-md items-center px-4 py-12">
      <Card glass className="w-full shadow-3d-floating border-border/80 animate-scale-in">
        <CardHeader className="space-y-3 text-center pb-2">
          <div className="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-gradient-to-br from-primary to-primary/60 text-primary-foreground shadow-3d-card border border-primary/30">
            <Bot className="h-6 w-6" />
          </div>
          <div>
            <CardTitle className="text-xl font-bold tracking-tight text-foreground">Welcome to OpenAgent</CardTitle>
            <p className="mt-1 text-xs text-muted-foreground">Sign in to your multi-agent developer platform</p>
          </div>
        </CardHeader>
        <CardContent className="space-y-4 pt-4">
          <div className="space-y-1.5">
            <Label className="text-xs uppercase tracking-wider font-semibold text-muted-foreground/80">Email</Label>
            <Input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="name@company.com" />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs uppercase tracking-wider font-semibold text-muted-foreground/80">Password</Label>
            <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" />
          </div>
          <Button className="w-full gap-2 active-tactile transition-transform h-10 mt-2" onClick={submit} disabled={loading || !email || !password}>
            {loading ? "Signing in..." : "Sign in"}
            {!loading && <ArrowRight className="h-4 w-4" />}
          </Button>
          <p className="text-center text-xs text-muted-foreground pt-2">
            No account yet? <Link className="text-primary font-semibold hover:underline" href="/register">Create account</Link>
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
