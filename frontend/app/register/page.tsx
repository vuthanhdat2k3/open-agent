"use client";

import * as React from "react";
import Link from "next/link";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { setAccessToken } from "@/lib/auth";

export default function RegisterPage() {
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [orgName, setOrgName] = React.useState("");
  const [loading, setLoading] = React.useState(false);

  async function submit() {
    setLoading(true);
    try {
      const res = await fetch("/api/auth/register", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password, org_name: orgName || undefined }),
      });
      if (!res.ok) throw new Error("Registration failed");
      const data = (await res.json()) as { access_token: string };
      setAccessToken(data.access_token);
      window.location.href = "/";
    } catch (error: any) {
      toast.error(error.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto flex min-h-[70vh] max-w-md items-center">
      <Card glass className="w-full">
        <CardHeader>
          <CardTitle>Create account</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-1.5">
            <Label>Email</Label>
            <Input value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label>Password</Label>
            <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label>Organization</Label>
            <Input value={orgName} onChange={(e) => setOrgName(e.target.value)} placeholder="Optional" />
          </div>
          <Button className="w-full" onClick={submit} disabled={loading || !email || !password}>
            {loading ? "Creating..." : "Create account"}
          </Button>
          <p className="text-center text-sm text-muted-foreground">
            Already have an account? <Link className="text-primary" href="/login">Sign in</Link>
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

