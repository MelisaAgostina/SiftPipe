import { useMemo, useState } from "react";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import { useScopeReview, useApproveScopeReview } from "@/lib/queries";
import type { ApiError } from "@/lib/api";
import { useLang } from "@/hooks/use-lang";
import type { ScopeReviewPage } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Callout } from "./Callout";
import { QueryState } from "./QueryState";

/**
 * Only ever rendered while waiting_for_scope_review is true (see
 * SecPipelineApp) - a discovered target's first crawl, paused before B5
 * turns anything it found into an attack target. Mattermost/NaViQ never
 * reach this state, so this screen never shows for them.
 */
export function ScopeReviewView() {
  const { t } = useLang();
  const scopeReviewQuery = useScopeReview();
  const approveMutation = useApproveScopeReview();

  const [approved, setApproved] = useState<Set<string>>(new Set());

  const toggle = (pageUrl: string) => {
    setApproved((prev) => {
      const next = new Set(prev);
      if (next.has(pageUrl)) next.delete(pageUrl);
      else next.add(pageUrl);
      return next;
    });
  };

  const submit = () => {
    approveMutation.mutate(
      { approved_pages: [...approved] },
      {
        onSuccess: () => {
          toast.success(t.scopeReviewView.approvalSent);
          setApproved(new Set());
        },
        onError: (err) => {
          const detail =
            (err as ApiError)?.detail ?? (err as Error)?.message ?? t.scopeReviewView.unknownError;
          toast.error(t.scopeReviewView.couldNotApprove(detail));
        },
      },
    );
  };

  return (
    <div className="space-y-6">
      <QueryState
        query={scopeReviewQuery}
        empty={(d) => d.pages.length === 0}
        emptyMessage={t.scopeReviewView.noPagesYet}
      >
        {(data) => (
          <Interactive
            pages={data.pages}
            endpoints={data.endpoints}
            approved={approved}
            onToggle={toggle}
            onSelectAll={() => setApproved(new Set(data.pages.map((p) => p.page_url)))}
            onSelectNone={() => setApproved(new Set())}
            onSubmit={submit}
            submitting={approveMutation.isPending}
          />
        )}
      </QueryState>
    </div>
  );
}

function Interactive({
  pages,
  endpoints,
  approved,
  onToggle,
  onSelectAll,
  onSelectNone,
  onSubmit,
  submitting,
}: {
  pages: ScopeReviewPage[];
  endpoints: string[];
  approved: Set<string>;
  onToggle: (pageUrl: string) => void;
  onSelectAll: () => void;
  onSelectNone: () => void;
  onSubmit: () => void;
  submitting: boolean;
}) {
  const { t } = useLang();
  const total = useMemo(() => pages.length, [pages]);

  return (
    <div className="space-y-4">
      <Callout>{t.scopeReviewView.pausedForReview}</Callout>

      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-muted-foreground">
          {t.scopeReviewView.selectedCount(approved.size, total)}
        </p>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            size="sm"
            className="px-2 text-xs"
            onClick={onSelectAll}
            disabled={submitting}
          >
            {t.scopeReviewView.selectAll}
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="px-2 text-xs"
            onClick={onSelectNone}
            disabled={submitting}
          >
            {t.scopeReviewView.deselectAll}
          </Button>
        </div>
      </div>

      <div className="grid gap-3">
        {pages.map((page) => (
          <Card key={page.page_url}>
            <CardHeader className="flex flex-row items-start gap-3 space-y-0">
              <Checkbox
                checked={approved.has(page.page_url)}
                onCheckedChange={() => onToggle(page.page_url)}
                disabled={submitting}
                className="mt-1"
              />
              <div className="min-w-0 flex-1">
                <CardTitle className="break-all text-sm">{page.page_url}</CardTitle>
                <CardDescription>
                  {page.forms.map((f, i) => (
                    <span key={i} className="mr-2">
                      {(f.method ?? "get").toUpperCase()} {f.action ?? "?"} ·{" "}
                      {f.field_names.filter(Boolean).join(", ") || "—"}
                    </span>
                  ))}
                  {page.input_field_names.length > 0 && (
                    <span>inputs: {page.input_field_names.filter(Boolean).join(", ")}</span>
                  )}
                  {page.forms.length === 0 && page.input_field_names.length === 0 && (
                    <span className="italic">{t.scopeReviewView.noFormsOrInputs}</span>
                  )}
                </CardDescription>
              </div>
            </CardHeader>
          </Card>
        ))}
      </div>

      {endpoints.length > 0 && (
        <div className="space-y-2">
          <label className="text-xs font-semibold tracking-wider text-muted-foreground">
            {t.scopeReviewView.endpointsHeading}
          </label>
          <div className="flex flex-wrap gap-2">
            {endpoints.map((e, i) => (
              <code key={i} className="rounded bg-muted px-2 py-1 text-xs">
                {e}
              </code>
            ))}
          </div>
        </div>
      )}

      <Button
        onClick={onSubmit}
        disabled={submitting || approved.size === 0}
        className="h-auto w-full whitespace-normal py-3 text-center leading-snug"
      >
        {submitting && <Loader2 className="h-4 w-4 shrink-0 animate-spin" />}
        {t.scopeReviewView.approveAndContinue(approved.size)}
      </Button>
    </div>
  );
}
