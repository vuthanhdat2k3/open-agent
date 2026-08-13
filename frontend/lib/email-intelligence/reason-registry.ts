export type ReasonSeverity = "info" | "warning" | "danger";

export type ReasonPresentation = {
  title: string;
  description: string;
  severity: ReasonSeverity;
};

const REASONS: Record<string, ReasonPresentation> = {
  "guard.prompt_injection_signal": {
    title: "Nội dung không tin cậy",
    description: "Nội dung được xử lý như dữ liệu, không phải chỉ dẫn hệ thống.",
    severity: "warning",
  },
  "routing.guard_restricted": {
    title: "Đã giới hạn routing",
    description: "Tác vụ tự động bị chặn và cần phê duyệt rõ ràng.",
    severity: "warning",
  },
  "risk.external_side_effect": {
    title: "Tác động bên ngoài",
    description: "Hành động có thể thay đổi dữ liệu hoặc dịch vụ bên ngoài.",
    severity: "danger",
  },
  "approval.expired": {
    title: "Approval đã hết hạn",
    description: "Cần tạo hoặc yêu cầu phê duyệt phiên bản mới.",
    severity: "warning",
  },
  "capability.only_proposal_owner_can_cancel": {
    title: "Chỉ chủ proposal được hủy",
    description: "Tài khoản hiện tại không có quyền hủy proposal này.",
    severity: "info",
  },
  "capability.processing_already_completed": {
    title: "Đã xử lý xong",
    description: "Tác vụ không còn ở trạng thái cho phép thao tác này.",
    severity: "info",
  },
  "connection.oauth_scope_missing": {
    title: "Thiếu quyền Google",
    description: "Cần cấp lại quyền kết nối để tiếp tục đồng bộ.",
    severity: "warning",
  },
};

export function presentReason(code: string | null | undefined): ReasonPresentation {
  return REASONS[code || ""] || {
    title: "Bị giới hạn bởi chính sách",
    description: "Hành động bị giới hạn bởi chính sách hệ thống.",
    severity: "warning",
  };
}

export function reasonRegistryVersion(): string {
  return "2026-08-13.1";
}
