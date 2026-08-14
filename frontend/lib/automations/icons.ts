import {
  BarChart3,
  CalendarClock,
  Inbox,
  MailSearch,
  SearchCheck,
  Sunset,
  Sunrise,
  Zap,
  type LucideIcon,
} from "lucide-react";

const icons: Record<string, LucideIcon> = {
  "calendar-clock": CalendarClock,
  "chart-no-axes-combined": BarChart3,
  inbox: Inbox,
  "mail-search": MailSearch,
  "search-check": SearchCheck,
  sunset: Sunset,
  sunrise: Sunrise,
};

export function workflowIcon(name: string): LucideIcon {
  return icons[name] ?? Zap;
}
