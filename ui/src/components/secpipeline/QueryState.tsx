import { Loader2 } from "lucide-react";
import type { ApiError } from "@/lib/api";
import { useLang } from "@/hooks/use-lang";
import { Callout } from "./Callout";

/**
 * Shared loading/error/empty three-way branch so it isn't duplicated across
 * every section in every view. `empty` decides what counts as "no data yet"
 * for that particular query (e.g. a missing result file vs. a zero-length array).
 */
export function QueryState<T>({
  query,
  empty,
  emptyMessage,
  children,
}: {
  query: { data: T | null | undefined; isLoading: boolean; isError: boolean; error: unknown };
  empty: (data: T) => boolean;
  emptyMessage: string;
  children: (data: T) => React.ReactNode;
}) {
  const { t } = useLang();

  if (query.isLoading) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-border bg-card px-4 py-3 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        {t.queryState.loading}
      </div>
    );
  }
  if (query.isError) {
    const detail =
      (query.error as ApiError)?.detail ?? (query.error as Error)?.message ?? t.common.unknown;
    return <Callout>{t.queryState.errorLoading(detail)}</Callout>;
  }
  if (query.data == null || empty(query.data)) {
    return <Callout>{emptyMessage}</Callout>;
  }
  return <>{children(query.data)}</>;
}
