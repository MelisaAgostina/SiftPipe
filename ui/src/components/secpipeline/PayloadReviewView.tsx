import { useMemo, useState } from "react";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import { usePipelineStatus, useB5, useValidatedPayloads, useValidatePayloads } from "@/lib/queries";
import type { ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Callout } from "./Callout";
import { QueryState } from "./QueryState";

export function PayloadReviewView({ onValidated }: { onValidated: () => void }) {
  const { data: status } = usePipelineStatus();
  const b5Query = useB5();
  const validatedQuery = useValidatedPayloads();
  const validateMutation = useValidatePayloads();

  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [comment, setComment] = useState("");

  const waiting = status?.waiting_for_human ?? false;

  const toggle = (idx: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  };

  const submit = () => {
    validateMutation.mutate(
      { approved_indices: [...selected].sort((a, b) => a - b), comment },
      {
        onSuccess: () => {
          toast.success("Validation sent — continuing with B7 → B9");
          setSelected(new Set());
          setComment("");
          onValidated();
        },
        onError: (err) => {
          const detail =
            (err as ApiError)?.detail ?? (err as Error)?.message ?? "unknown error";
          toast.error(`Could not validate: ${detail}`);
        },
      },
    );
  };

  return (
    <div className="space-y-6">
      <QueryState
        query={b5Query}
        empty={(d) => d.payloads.length === 0}
        emptyMessage="No payloads generated yet. Run the pipeline (B3→B5) first."
      >
        {(b5) =>
          !waiting ? (
            <AlreadyPastB6 validatedQuery={validatedQuery} />
          ) : (
            <InteractiveReview
              payloads={b5.payloads}
              selected={selected}
              onToggle={toggle}
              onSelectAll={() =>
                setSelected(
                  new Set(
                    b5.payloads.map((_, i) => i).filter((i) => b5.payloads[i].payloads.length > 0),
                  ),
                )
              }
              onSelectNone={() => setSelected(new Set())}
              comment={comment}
              onCommentChange={setComment}
              onSubmit={submit}
              submitting={validateMutation.isPending}
            />
          )
        }
      </QueryState>
    </div>
  );
}

function AlreadyPastB6({
  validatedQuery,
}: {
  validatedQuery: ReturnType<typeof useValidatedPayloads>;
}) {
  return (
    <QueryState
      query={validatedQuery}
      empty={(d) => d.payloads.length === 0}
      emptyMessage="Waiting for the pipeline to reach B6…"
    >
      {(validated) => (
        <div className="space-y-3">
          <Callout>
            Already validated — {validated.payloads.length} target(s) approved in this run.
          </Callout>
          {validated.comment && (
            <div className="rounded border border-border bg-muted/40 px-3 py-2 text-xs text-foreground">
              <span className="font-semibold text-muted-foreground">Reviewer note: </span>
              {validated.comment}
            </div>
          )}
          <div className="grid gap-3">
            {validated.payloads.map((g, i) => (
              <Card key={i}>
                <CardHeader>
                  <CardTitle className="text-sm">
                    {g.target_desc ?? g.target ?? "unknown target"}
                  </CardTitle>
                  <CardDescription>{g.rationale}</CardDescription>
                </CardHeader>
                <CardContent className="flex flex-wrap gap-2 pt-0">
                  {g.payloads.map((p, j) => (
                    <code key={j} className="rounded bg-muted px-2 py-1 text-xs">
                      {p}
                    </code>
                  ))}
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      )}
    </QueryState>
  );
}

function InteractiveReview({
  payloads,
  selected,
  onToggle,
  onSelectAll,
  onSelectNone,
  comment,
  onCommentChange,
  onSubmit,
  submitting,
}: {
  payloads: {
    target: string | null;
    target_desc: string | null;
    rationale: string;
    payloads: string[];
    owasp_category: string | null;
    cwe_id: string | null;
    page_url: string | null;
    field_name: string | null;
  }[];
  selected: Set<number>;
  onToggle: (i: number) => void;
  onSelectAll: () => void;
  onSelectNone: () => void;
  comment: string;
  onCommentChange: (v: string) => void;
  onSubmit: () => void;
  submitting: boolean;
}) {
  const selectableCount = useMemo(
    () => payloads.filter((g) => g.payloads.length > 0).length,
    [payloads],
  );

  return (
    <div className="space-y-4">
      <Callout>
        The pipeline is paused, waiting for review. Choose which payloads to run against
        Mattermost in B7.
      </Callout>

      <div className="flex items-center justify-between">
        <p className="text-xs text-muted-foreground">
          {selected.size} of {selectableCount} selected
        </p>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={onSelectAll} disabled={submitting}>
            Select all
          </Button>
          <Button variant="outline" size="sm" onClick={onSelectNone} disabled={submitting}>
            Deselect all
          </Button>
        </div>
      </div>

      <div className="grid gap-3">
        {payloads.map((g, i) => {
          const disabled = g.payloads.length === 0;
          return (
            <Card key={i} className={disabled ? "opacity-60" : undefined}>
              <CardHeader className="flex flex-row items-start gap-3 space-y-0">
                <Checkbox
                  checked={selected.has(i)}
                  onCheckedChange={() => onToggle(i)}
                  disabled={disabled || submitting}
                  className="mt-1"
                />
                <div className="min-w-0 flex-1">
                  <CardTitle className="text-sm">
                    {g.target_desc ?? g.target ?? "unknown target"}
                  </CardTitle>
                  <CardDescription>
                    {[g.owasp_category, g.cwe_id, g.field_name, g.page_url]
                      .filter(Boolean)
                      .join(" · ")}
                  </CardDescription>
                </div>
              </CardHeader>
              <CardContent className="space-y-2 pt-0">
                <p className="text-xs text-muted-foreground">{g.rationale}</p>
                <div className="flex flex-wrap gap-2">
                  {g.payloads.length === 0 ? (
                    <span className="text-xs italic text-muted-foreground">
                      no payloads (generation failed)
                    </span>
                  ) : (
                    g.payloads.map((p, j) => (
                      <code key={j} className="rounded bg-muted px-2 py-1 text-xs">
                        {p}
                      </code>
                    ))
                  )}
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <div className="space-y-2">
        <label className="text-xs font-semibold tracking-wider text-muted-foreground">
          COMMENT (OPTIONAL)
        </label>
        <Textarea
          value={comment}
          onChange={(e) => onCommentChange(e.target.value)}
          placeholder="Notes about this validation..."
          disabled={submitting}
        />
      </div>

      <Button onClick={onSubmit} disabled={submitting || selected.size === 0} className="w-full">
        {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
        Validate {selected.size} payload(s) and continue to B7
      </Button>
    </div>
  );
}
