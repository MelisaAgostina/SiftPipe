import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { act, render, screen, fireEvent } from "@testing-library/react";

vi.mock("@/lib/queries", () => ({
  useCheckTargetName: vi.fn(),
  useCheckEnvVar: vi.fn(),
  useStartDiscovery: vi.fn(),
  useDiscoveryStatus: vi.fn(),
  useSetTarget: vi.fn(),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import {
  useCheckTargetName,
  useCheckEnvVar,
  useStartDiscovery,
  useDiscoveryStatus,
  useSetTarget,
} from "@/lib/queries";
import { toast } from "sonner";
import { DiscoverTargetDialog } from "./DiscoverTargetDialog";

const startMutate = vi.fn();
const setTargetMutate = vi.fn();

function loadedQuery<T>(data: T) {
  return { data, isLoading: false };
}

async function advanceDebounce() {
  await act(async () => {
    vi.advanceTimersByTime(500);
  });
}

async function type(input: HTMLElement, value: string) {
  fireEvent.change(input, { target: { value } });
  await advanceDebounce();
}

describe("DiscoverTargetDialog", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    startMutate.mockClear();
    setTargetMutate.mockClear();
    vi.mocked(toast.error).mockClear();

    vi.mocked(useCheckTargetName).mockReturnValue(loadedQuery({ available: true }) as never);
    vi.mocked(useCheckEnvVar).mockReturnValue(loadedQuery({ name: "", present: true }) as never);
    vi.mocked(useStartDiscovery).mockReturnValue({
      mutate: startMutate,
      isPending: false,
    } as never);
    vi.mocked(useDiscoveryStatus).mockReturnValue({ data: undefined } as never);
    vi.mocked(useSetTarget).mockReturnValue({ mutate: setTargetMutate } as never);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  function openDialog() {
    render(<DiscoverTargetDialog />);
    fireEvent.click(screen.getByRole("button", { name: /add new target/i }));
  }

  async function goToStep2(name = "juiceshop") {
    openDialog();
    await type(screen.getByLabelText(/target name/i), name);
    fireEvent.click(screen.getByRole("button", { name: /^next$/i }));
  }

  async function goToStep3(baseUrl = "http://localhost:3000", loginPath = "/login") {
    await goToStep2();
    fireEvent.change(screen.getByLabelText(/base url/i), { target: { value: baseUrl } });
    fireEvent.change(screen.getByLabelText(/login path/i), { target: { value: loginPath } });
    fireEvent.click(screen.getByRole("button", { name: /^next$/i }));
  }

  it("opens on click and starts on step 1 with Next disabled until a name is typed", () => {
    openDialog();

    expect(screen.getByText(/step 1 of 3/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^next$/i })).toBeDisabled();
  });

  it("blocks step 1 when the name is already taken", async () => {
    vi.mocked(useCheckTargetName).mockReturnValue(loadedQuery({ available: false }) as never);
    openDialog();

    await type(screen.getByLabelText(/target name/i), "mattermost");

    expect(screen.getByText(/already exists/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^next$/i })).toBeDisabled();
  });

  it("blocks step 1 on a name with characters the backend would reject", async () => {
    // Mirrors blocks/targets.py's is_valid_target_name() - catches a bad
    // name (spaces, path separators, uppercase) before it's ever sent,
    // rather than only failing at submit.
    openDialog();

    await type(screen.getByLabelText(/target name/i), "../../etc/passwd");

    expect(screen.getByText(/lowercase letters, digits/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^next$/i })).toBeDisabled();
  });

  it("blocks step 2 on an invalid base URL or login path", async () => {
    await goToStep2();

    fireEvent.change(screen.getByLabelText(/base url/i), { target: { value: "not-a-url" } });
    fireEvent.change(screen.getByLabelText(/login path/i), { target: { value: "login" } });

    expect(screen.getByText(/enter a full url/i)).toBeInTheDocument();
    expect(screen.getByText(/should start with/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^next$/i })).toBeDisabled();
  });

  it("shows a live preview of the full login URL once both fields are valid", async () => {
    await goToStep2();

    fireEvent.change(screen.getByLabelText(/base url/i), {
      target: { value: "http://localhost:3000" },
    });
    fireEvent.change(screen.getByLabelText(/login path/i), { target: { value: "/login" } });

    expect(screen.getByText("http://localhost:3000/login")).toBeInTheDocument();
  });

  it("rejects a lowercase or invalid env var name on step 3", async () => {
    await goToStep3();

    fireEvent.change(screen.getByLabelText(/username variable/i), {
      target: { value: "bad name!" },
    });

    expect(screen.getByText(/A-Z, 0-9, and underscores/i)).toBeInTheDocument();
  });

  it("shows whether each credential variable is present in the server's .env", async () => {
    vi.mocked(useCheckEnvVar).mockImplementation(((name: string) =>
      loadedQuery({ name, present: name === "JS_USER" })) as typeof useCheckEnvVar);
    await goToStep3();

    await type(screen.getByLabelText(/username variable/i), "JS_USER");
    await type(screen.getByLabelText(/password variable/i), "JS_PASS");

    expect(screen.getByText(/found in your environment/i)).toBeInTheDocument();
    expect(screen.getByText(/not set in your \.env yet/i)).toBeInTheDocument();
  });

  it("submits the full form and shows the running state", async () => {
    await goToStep3();
    await type(screen.getByLabelText(/username variable/i), "JS_USER");
    await type(screen.getByLabelText(/password variable/i), "JS_PASS");

    fireEvent.click(screen.getByRole("button", { name: /start discovery/i }));

    expect(startMutate).toHaveBeenCalledTimes(1);
    const [body] = startMutate.mock.calls[0];
    expect(body).toEqual({
      name: "juiceshop",
      base_url: "http://localhost:3000",
      login_path: "/login",
      username_env: "JS_USER",
      password_env: "JS_PASS",
    });
  });

  it("shows a spinner while discovery is running", async () => {
    vi.mocked(useDiscoveryStatus).mockReturnValue(
      loadedQuery({ running: true, error: null, result: null }) as never,
    );
    await goToStep3();
    await type(screen.getByLabelText(/username variable/i), "JS_USER");
    await type(screen.getByLabelText(/password variable/i), "JS_PASS");
    fireEvent.click(screen.getByRole("button", { name: /start discovery/i }));

    expect(screen.getByText(/reaching the login page/i)).toBeInTheDocument();
  });

  it("shows the discovered selectors and a Switch to it button on a successful login", async () => {
    vi.mocked(useDiscoveryStatus).mockReturnValue(
      loadedQuery({
        running: false,
        error: null,
        result: {
          name: "juiceshop",
          login_succeeded: true,
          error: null,
          login_id_selectors: ["input#email"],
          password_selectors: ["input#password"],
          submit_selectors: ["button[type='submit']"],
        },
      }) as never,
    );
    await goToStep3();
    await type(screen.getByLabelText(/username variable/i), "JS_USER");
    await type(screen.getByLabelText(/password variable/i), "JS_PASS");
    fireEvent.click(screen.getByRole("button", { name: /start discovery/i }));

    expect(screen.getByText("input#email")).toBeInTheDocument();
    const switchButton = screen.getByRole("button", { name: /switch to it/i });
    fireEvent.click(switchButton);
    expect(setTargetMutate).toHaveBeenCalledWith({ name: "juiceshop" }, expect.anything());
  });

  it("shows the failure reason and no Switch to it button when login didn't succeed", async () => {
    vi.mocked(useDiscoveryStatus).mockReturnValue(
      loadedQuery({
        running: false,
        error: null,
        result: {
          name: "juiceshop",
          login_succeeded: false,
          error: "still_on_login_page",
          login_id_selectors: ["input#email"],
          password_selectors: [],
          submit_selectors: [],
        },
      }) as never,
    );
    await goToStep3();
    await type(screen.getByLabelText(/username variable/i), "JS_USER");
    await type(screen.getByLabelText(/password variable/i), "JS_PASS");
    fireEvent.click(screen.getByRole("button", { name: /start discovery/i }));

    expect(screen.getByText(/still_on_login_page/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /switch to it/i })).not.toBeInTheDocument();
  });
});
