"use client";

import * as React from "react";
import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from "lucide-react";
import { useTranslation } from "@/lib/i18n";
import { Button } from "@/components/ui/button";

export interface DataPaginationProps {
  page: number;
  pageSize: number;
  totalItems: number;
  onPageChange: (page: number) => void;
  onPageSizeChange?: (pageSize: number) => void;
  pageSizeOptions?: number[];
  className?: string;
  hideOnSinglePage?: boolean;
  compact?: boolean;
}

export function DataPagination({
  page,
  pageSize,
  totalItems,
  onPageChange,
  onPageSizeChange,
  pageSizeOptions = [10, 20, 50],
  className = "",
  hideOnSinglePage = true,
  compact = false,
}: DataPaginationProps) {
  const { t, locale } = useTranslation();
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));

  // Automatically hide pagination if there's only 1 page (or 0 items) and hideOnSinglePage is true
  if (hideOnSinglePage && (totalItems <= pageSize || totalPages <= 1)) {
    return null;
  }

  const currentPage = Math.min(Math.max(1, page), totalPages);
  const startItem = totalItems === 0 ? 0 : (currentPage - 1) * pageSize + 1;
  const endItem = Math.min(currentPage * pageSize, totalItems);

  const getPageNumbers = () => {
    const pages: (number | string)[] = [];
    if (totalPages <= 5) {
      for (let i = 1; i <= totalPages; i++) pages.push(i);
    } else {
      if (currentPage <= 3) {
        pages.push(1, 2, 3, 4, "...", totalPages);
      } else if (currentPage >= totalPages - 2) {
        pages.push(1, "...", totalPages - 3, totalPages - 2, totalPages - 1, totalPages);
      } else {
        pages.push(1, "...", currentPage - 1, currentPage, currentPage + 1, "...", totalPages);
      }
    }
    return pages;
  };

  if (compact) {
    return (
      <div className={`flex items-center justify-between gap-2 border-t border-border/60 pt-2 text-xs text-muted-foreground ${className}`}>
        <span>
          {currentPage} / {totalPages} ({totalItems} {locale === "vi" ? "kết quả" : "items"})
        </span>
        <div className="flex items-center gap-1">
          <Button
            variant="outline"
            size="sm"
            className="h-6 w-6 p-0"
            onClick={() => onPageChange(currentPage - 1)}
            disabled={currentPage === 1}
            aria-label="Previous"
          >
            <ChevronLeft className="h-3 w-3" />
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="h-6 w-6 p-0"
            onClick={() => onPageChange(currentPage + 1)}
            disabled={currentPage === totalPages}
            aria-label="Next"
          >
            <ChevronRight className="h-3 w-3" />
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div
      className={`flex flex-col items-center justify-between gap-3 border-t border-border/60 px-2 py-3 text-xs text-muted-foreground sm:flex-row ${className}`}
    >
      <div className="flex items-center gap-2">
        {locale === "vi" ? (
          <span>
            {t("common.showing", "Hiển thị")}{" "}
            <span className="font-medium text-foreground">{startItem}</span> -{" "}
            <span className="font-medium text-foreground">{endItem}</span>{" "}
            {t("common.of", "trên")}{" "}
            <span className="font-medium text-foreground">{totalItems}</span>{" "}
            {t("common.results", "kết quả")}
          </span>
        ) : (
          <span>
            {t("common.showing", "Showing")}{" "}
            <span className="font-medium text-foreground">{startItem}</span> {t("common.to", "to")} {" "}
            <span className="font-medium text-foreground">{endItem}</span>{" "}
            {t("common.of", "of")}{" "}
            <span className="font-medium text-foreground">{totalItems}</span>{" "}
            {t("common.results", "results")}
          </span>
        )}

        {onPageSizeChange && (
          <div className="flex items-center gap-1.5 pl-3 border-l border-border/60">
            <span>{t("common.rowsPerPage", locale === "vi" ? "Mỗi trang:" : "Per page:")}</span>
            <select
              value={pageSize}
              onChange={(e) => {
                onPageSizeChange(Number(e.target.value));
                onPageChange(1);
              }}
              className="h-7 rounded border border-border bg-background px-2 text-xs text-foreground focus:border-primary focus:outline-none"
            >
              {pageSizeOptions.map((opt) => (
                <option key={opt} value={opt}>
                  {opt}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      <div className="flex items-center gap-1">
        <Button
          variant="outline"
          size="sm"
          className="h-7 w-7 p-0"
          onClick={() => onPageChange(1)}
          disabled={currentPage === 1}
          aria-label="First page"
        >
          <ChevronsLeft className="h-3.5 w-3.5" />
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="h-7 w-7 p-0"
          onClick={() => onPageChange(currentPage - 1)}
          disabled={currentPage === 1}
          aria-label="Previous page"
        >
          <ChevronLeft className="h-3.5 w-3.5" />
        </Button>

        <div className="flex items-center gap-1 px-1">
          {getPageNumbers().map((p, idx) =>
            typeof p === "number" ? (
              <Button
                key={idx}
                variant={currentPage === p ? "default" : "outline"}
                size="sm"
                className={`h-7 min-w-[28px] px-2 text-xs ${
                  currentPage === p
                    ? "bg-primary text-primary-foreground font-semibold"
                    : "text-muted-foreground hover:text-foreground"
                }`}
                onClick={() => onPageChange(p)}
              >
                {p}
              </Button>
            ) : (
              <span key={idx} className="px-1 text-muted-foreground">
                ...
              </span>
            ),
          )}
        </div>

        <Button
          variant="outline"
          size="sm"
          className="h-7 w-7 p-0"
          onClick={() => onPageChange(currentPage + 1)}
          disabled={currentPage === totalPages || totalItems === 0}
          aria-label="Next page"
        >
          <ChevronRight className="h-3.5 w-3.5" />
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="h-7 w-7 p-0"
          onClick={() => onPageChange(totalPages)}
          disabled={currentPage === totalPages || totalItems === 0}
          aria-label="Last page"
        >
          <ChevronsRight className="h-3.5 w-3.5" />
        </Button>
      </div>
    </div>
  );
}
