import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryState } from "./QueryState";

function query(
  overrides: Partial<{
    data: unknown;
    isLoading: boolean;
    isError: boolean;
    error: unknown;
  }> = {},
) {
  return { data: undefined, isLoading: false, isError: false, error: null, ...overrides };
}

describe("QueryState", () => {
  it("shows a loading indicator while the query is loading, even if data/error are also set", () => {
    render(
      <QueryState query={query({ isLoading: true })} empty={() => false} emptyMessage="empty">
        {() => <p>content</p>}
      </QueryState>,
    );

    expect(screen.getByText(/loading/i)).toBeInTheDocument();
    expect(screen.queryByText("content")).not.toBeInTheDocument();
  });

  it("shows the backend's error detail when the query fails", () => {
    render(
      <QueryState
        query={query({ isError: true, error: { detail: "results file missing" } })}
        empty={() => false}
        emptyMessage="empty"
      >
        {() => <p>content</p>}
      </QueryState>,
    );

    expect(screen.getByText(/results file missing/i)).toBeInTheDocument();
  });

  it("falls back to a generic message when the error carries neither detail nor a message", () => {
    render(
      <QueryState
        query={query({ isError: true, error: {} })}
        empty={() => false}
        emptyMessage="empty"
      >
        {() => <p>content</p>}
      </QueryState>,
    );

    expect(screen.getByText(/unknown/i)).toBeInTheDocument();
  });

  it("shows the caller's empty message when data is null", () => {
    render(
      <QueryState query={query({ data: null })} empty={() => false} emptyMessage="nothing here yet">
        {() => <p>content</p>}
      </QueryState>,
    );

    expect(screen.getByText("nothing here yet")).toBeInTheDocument();
  });

  it("shows the caller's empty message when the caller's own empty() predicate says so", () => {
    render(
      <QueryState
        query={query({ data: { items: [] } }) as never}
        empty={(d: { items: unknown[] }) => d.items.length === 0}
        emptyMessage="nothing here yet"
      >
        {() => <p>content</p>}
      </QueryState>,
    );

    expect(screen.getByText("nothing here yet")).toBeInTheDocument();
  });

  it("renders the children render-prop with the real data once loaded and non-empty", () => {
    render(
      <QueryState
        query={query({ data: { items: [1, 2] } }) as never}
        empty={(d: { items: unknown[] }) => d.items.length === 0}
        emptyMessage="nothing here yet"
      >
        {(d: { items: number[] }) => <p>{d.items.length} items</p>}
      </QueryState>,
    );

    expect(screen.getByText("2 items")).toBeInTheDocument();
  });

  it("checks isLoading and isError before ever calling the empty() predicate", () => {
    // Real ordering this locks in: a query that's still loading (or errored)
    // but already carries stale/partial data shouldn't have empty() run
    // against that stale data - loading/error must win first.
    let emptyCalled = false;
    render(
      <QueryState
        query={query({ isLoading: true, data: { items: [] } })}
        empty={() => {
          emptyCalled = true;
          return true;
        }}
        emptyMessage="empty"
      >
        {() => <p>content</p>}
      </QueryState>,
    );

    expect(emptyCalled).toBe(false);
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });
});
