export type ReasonSeverity = "info" | "warning" | "danger";
export type ReasonLocale = "vi" | "en";

export type ReasonPresentation = {
  title: string;
  description: string;
  severity: ReasonSeverity;
};

type ReasonText = { title: string; description: string };
type ReasonEntry = { severity: ReasonSeverity; vi: ReasonText; en: ReasonText };

const REASONS: Record<string, ReasonEntry> = {
  "guard.prompt_injection_signal": {
    severity: "warning",
    vi: {
      title: "Nội dung không tin cậy",
      description: "Nội dung được xử lý như dữ liệu, không phải chỉ dẫn hệ thống.",
    },
    en: {
      title: "Untrusted content",
      description: "Content is treated as data, not as system instructions.",
    },
  },
  "routing.guard_restricted": {
    severity: "warning",
    vi: {
      title: "Đã giới hạn routing",
      description: "Tác vụ tự động bị chặn và cần phê duyệt rõ ràng.",
    },
    en: {
      title: "Routing restricted",
      description: "The automated task was blocked and requires explicit approval.",
    },
  },
  "risk.external_side_effect": {
    severity: "danger",
    vi: {
      title: "Tác động bên ngoài",
      description: "Hành động có thể thay đổi dữ liệu hoặc dịch vụ bên ngoài.",
    },
    en: {
      title: "External side effect",
      description: "This action may change external data or services.",
    },
  },
  "approval.expired": {
    severity: "warning",
    vi: {
      title: "Approval đã hết hạn",
      description: "Cần tạo hoặc yêu cầu phê duyệt phiên bản mới.",
    },
    en: {
      title: "Approval expired",
      description: "A new approval version must be created or requested.",
    },
  },
  "capability.only_proposal_owner_can_cancel": {
    severity: "info",
    vi: {
      title: "Chỉ chủ proposal được hủy",
      description: "Tài khoản hiện tại không có quyền hủy proposal này.",
    },
    en: {
      title: "Only the proposal owner can cancel",
      description: "The current account does not have permission to cancel this proposal.",
    },
  },
  "capability.processing_already_completed": {
    severity: "info",
    vi: {
      title: "Đã xử lý xong",
      description: "Tác vụ không còn ở trạng thái cho phép thao tác này.",
    },
    en: {
      title: "Already processed",
      description: "The task is no longer in a state that allows this action.",
    },
  },
  "connection.oauth_scope_missing": {
    severity: "warning",
    vi: {
      title: "Thiếu quyền Google",
      description: "Cần cấp lại quyền kết nối để tiếp tục đồng bộ.",
    },
    en: {
      title: "Missing Google permission",
      description: "Re-grant the connection permission to continue syncing.",
    },
  },
};

const FALLBACK: Record<ReasonLocale, ReasonText> = {
  vi: {
    title: "Bị giới hạn bởi chính sách",
    description: "Hành động bị giới hạn bởi chính sách hệ thống.",
  },
  en: {
    title: "Restricted by policy",
    description: "This action is restricted by system policy.",
  },
};

export function presentReason(
  code: string | null | undefined,
  locale: ReasonLocale = "vi",
): ReasonPresentation {
  const entry = REASONS[code || ""];
  if (!entry) return { ...FALLBACK[locale], severity: "warning" };
  return { ...entry[locale], severity: entry.severity };
}

export function reasonRegistryVersion(): string {
  return "2026-08-13.1";
}
