"use client";

import * as React from "react";
import { Check, X, Info } from "lucide-react";
import { validateZitadelPassword } from "@/lib/password";
import { useTranslation } from "@/lib/i18n";

interface PasswordComplexityIndicatorProps {
  password: string;
  showDefaultNote?: boolean;
}

export function PasswordComplexityIndicator({
  password,
  showDefaultNote = true,
}: PasswordComplexityIndicatorProps) {
  const { tx } = useTranslation();
  const trimmed = password.trim();

  if (!trimmed) {
    if (!showDefaultNote) return null;
    return (
      <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground pt-1">
        <Info className="h-3.5 w-3.5 shrink-0 text-primary" />
        <span>
          {tx(
            "Yêu cầu 8+ ký tự (hoa, thường, số, ký tự đặc biệt). Mặc định khi để trống: OpenAgent@2026",
            "Requires 8+ chars (uppercase, lowercase, number, symbol). Default when blank: OpenAgent@2026"
          )}
        </span>
      </div>
    );
  }

  const { hasMinLength, hasUppercase, hasLowercase, hasNumber, hasSymbol, isValid } =
    validateZitadelPassword(trimmed);

  const rules = [
    { label: tx("8+ ký tự", "8+ chars"), passed: hasMinLength },
    { label: tx("Chữ hoa (A-Z)", "Uppercase (A-Z)"), passed: hasUppercase },
    { label: tx("Chữ thường (a-z)", "Lowercase (a-z)"), passed: hasLowercase },
    { label: tx("Số (0-9)", "Number (0-9)"), passed: hasNumber },
    { label: tx("Ký tự đặc biệt (@, #, ...)", "Symbol (@, #, ...)"), passed: hasSymbol },
  ];

  return (
    <div className="space-y-1.5 pt-1.5">
      <div className="flex flex-wrap gap-1.5">
        {rules.map((rule, idx) => (
          <span
            key={idx}
            className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] font-medium transition-colors ${
              rule.passed
                ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20"
                : "bg-muted text-muted-foreground border border-border"
            }`}
          >
            {rule.passed ? (
              <Check className="h-2.5 w-2.5 text-emerald-500" />
            ) : (
              <X className="h-2.5 w-2.5 text-muted-foreground" />
            )}
            {rule.label}
          </span>
        ))}
      </div>
      {!isValid && (
        <p className="text-[11px] text-amber-500 font-medium">
          {tx(
            "Mật khẩu cần thỏa mãn tất cả tiêu chí trên để ZITADEL Identity Provider chấp nhận.",
            "Password must satisfy all criteria above for ZITADEL Identity Provider."
          )}
        </p>
      )}
    </div>
  );
}
