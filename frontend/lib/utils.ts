import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export const apiBaseUrl =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export function cn(...classes: ClassValue[]): string {
  return twMerge(clsx(classes));
}
