"use client";

import * as React from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { toast } from "sonner";
import { AlertCircle, ArrowRight, Bot, ShieldAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Input, Label } from "@/components/ui/input";
import { setAccessToken } from "@/lib/auth";

import { useTranslation } from "@/lib/i18n";
import { LanguageToggle } from "@/components/language-toggle";

const ERROR_MESSAGES_VI: Record<string, { title: string; desc: string }> = {
  ORGANIZATION_CONTEXT_REQUIRED: {
    title: "Tài khoản chưa thuộc tổ chức nào",
    desc: "Tài khoản của bạn hiện không thuộc bất kỳ tổ chức nào hoặc đã bị xóa khỏi tổ chức. Vui lòng liên hệ Quản trị viên (Admin) để được mời tham gia.",
  },
  ACCOUNT_NOT_PROVISIONED: {
    title: "Tài khoản chưa được kích hoạt",
    desc: "Tài khoản của bạn đã bị vô hiệu hóa hoặc chưa được cấp quyền truy cập. Vui lòng liên hệ Quản trị viên để được hỗ trợ.",
  },
  ORGANIZATION_CONTEXT_MISMATCH: {
    title: "Không khớp thông tin tổ chức",
    desc: "Danh tính xác thực không khớp với tổ chức bạn đang yêu cầu truy cập.",
  },
  CODE_EXCHANGE_FAILED: {
    title: "Xác thực không thành công",
    desc: "Không thể trao đổi mã xác thực với máy chủ danh tính ZITADEL. Vui lòng thử lại.",
  },
};

const ERROR_MESSAGES_EN: Record<string, { title: string; desc: string }> = {
  ORGANIZATION_CONTEXT_REQUIRED: {
    title: "No Organization Assigned",
    desc: "Your account is not assigned to any organization. Please contact your administrator for an invitation.",
  },
  ACCOUNT_NOT_PROVISIONED: {
    title: "Account Not Activated",
    desc: "Your account is deactivated or not yet provisioned. Please contact your system administrator.",
  },
  ORGANIZATION_CONTEXT_MISMATCH: {
    title: "Organization Mismatch",
    desc: "The authenticated identity does not match the organization context you are accessing.",
  },
  CODE_EXCHANGE_FAILED: {
    title: "Authentication Failed",
    desc: "Could not exchange authentication tokens with the identity server. Please retry.",
  },
};

export default function LoginPage() {
  const { t, locale } = useTranslation();
  const searchParams = useSearchParams();
  const errorParam = searchParams.get("error");
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

  const errDict = locale === "vi" ? ERROR_MESSAGES_VI : ERROR_MESSAGES_EN;
  const errorInfo = errorParam
    ? errDict[errorParam] || {
        title: locale === "vi" ? "Đăng nhập không thành công" : "Sign In Failed",
        desc: locale === "vi" ? `Đã xảy ra lỗi xác thực (${errorParam}). Vui lòng liên hệ quản trị viên để được hỗ trợ.` : `An authentication error occurred (${errorParam}). Please contact your administrator.`,
      }
    : null;

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      if (!response.ok) throw new Error("Invalid email or password");
      const data = (await response.json()) as { access_token: string };
      setAccessToken(data.access_token);
      window.location.replace("/");
    } catch (error: unknown) {
      toast.error(error instanceof Error ? error.message : "Unable to sign in");
    } finally {
      setLoading(false);
    }
  }

  if (zitadelEnabled) {
    return (
      <div className="relative mx-auto flex min-h-dvh max-w-md flex-col justify-center px-4 py-12">
        <div className="absolute right-4 top-4">
          <LanguageToggle />
        </div>
        <Card className="w-full border-border/80 shadow-3d-floating">
          <CardHeader className="space-y-3 pb-3 text-center">
            <div className="mx-auto grid h-12 w-12 place-items-center rounded-xl bg-primary text-primary-foreground shadow-card">
              <Bot className="h-6 w-6" aria-hidden="true" />
            </div>
            <div>
              <CardTitle className="text-xl">
                {locale === "vi" ? "Đăng nhập OpenAgent" : "Sign in to OpenAgent"}
              </CardTitle>
              <p className="mt-2 text-sm text-muted-foreground">
                {locale === "vi"
                  ? "Xác thực danh tính doanh nghiệp tập trung qua Single Sign-On."
                  : "Authentication is managed by your organization identity provider."}
              </p>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {errorInfo && (
              <Alert variant="destructive" className="border-destructive/40 bg-destructive/10 text-left">
                <AlertCircle className="h-4 w-4" />
                <AlertTitle className="text-sm font-semibold">{errorInfo.title}</AlertTitle>
                <AlertDescription className="mt-1 text-xs leading-relaxed text-destructive/90">
                  {errorInfo.desc}
                </AlertDescription>
              </Alert>
            )}
            <Button
              type="button"
              className="h-11 w-full gap-2 active-tactile"
              onClick={() => {
                window.location.href = "/api/auth/login";
              }}
            >
              {locale === "vi" ? "Tiếp tục qua SSO Doanh nghiệp" : "Continue with organization SSO"}
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="relative mx-auto flex min-h-dvh max-w-md flex-col justify-center px-4 py-12">
      <div className="absolute right-4 top-4">
        <LanguageToggle />
      </div>
      <Card className="w-full border-border/80 shadow-3d-floating">
        <CardHeader className="space-y-3 pb-3 text-center">
          <div className="mx-auto grid h-12 w-12 place-items-center rounded-xl bg-primary text-primary-foreground shadow-card">
            <Bot className="h-6 w-6" aria-hidden="true" />
          </div>
          <div>
            <CardTitle className="text-xl">
              {locale === "vi" ? "Đăng nhập nội bộ đã tắt" : "Local authentication is disabled"}
            </CardTitle>
            <p className="mt-2 text-sm text-muted-foreground">
              {locale === "vi"
                ? "Vui lòng sử dụng nhà cung cấp danh tính tổ chức để đăng nhập."
                : "Use the configured organization identity provider to sign in."}
            </p>
          </div>
        </CardHeader>
      </Card>
    </div>
  );
}
