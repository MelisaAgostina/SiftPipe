import { useEffect, useState } from "react";
import { toast } from "sonner";
import { CheckCircle2, CirclePlus, Loader2, XCircle } from "lucide-react";
import {
  useCheckEnvVar,
  useCheckTargetName,
  useDiscoveryStatus,
  useSetTarget,
  useStartDiscovery,
} from "@/lib/queries";
import type { ApiError } from "@/lib/api";
import { useLang } from "@/hooks/use-lang";
import type { Strings } from "@/lib/strings";
import type { DiscoveryResult } from "@/lib/types";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const URL_RE = /^https?:\/\/[^/]+$/;
const PATH_RE = /^\/\S*$/;
const ENV_NAME_RE = /^[A-Z0-9_]+$/;
// Mirrors blocks/targets.py's is_valid_target_name() - the actual backend
// rule, not just cosmetic. Anything else gets rejected server-side anyway
// (a real path-traversal name like "../../etc/passwd" must never reach a
// targets/<name>.json path unvalidated); this just surfaces that as an
// inline error instead of a failed submit.
const NAME_RE = /^[a-z0-9_-]{1,64}$/;

function useDebounced<T>(value: T, delay = 400): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(id);
  }, [value, delay]);
  return debounced;
}

type Step = 1 | 2 | 3;

/**
 * Runs discover_target.py's discover() from the browser instead of a
 * terminal - a real Playwright login attempt plus one Anthropic call, so
 * submitting this form is the confirmation, the same way clicking "Run
 * Pipeline" already is elsewhere in this app. Only ever produces a new
 * targets/<name>.json; Mattermost/NaViQ aren't reachable from here.
 */
export function DiscoverTargetDialog() {
  const { t } = useLang();
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState<Step>(1);
  const [name, setName] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [loginPath, setLoginPath] = useState("/login");
  const [usernameEnv, setUsernameEnv] = useState("");
  const [passwordEnv, setPasswordEnv] = useState("");
  const [submitted, setSubmitted] = useState(false);

  const debouncedName = useDebounced(name);
  const debouncedUsernameEnv = useDebounced(usernameEnv);
  const debouncedPasswordEnv = useDebounced(passwordEnv);

  const nameCheck = useCheckTargetName(debouncedName);
  const usernameEnvCheck = useCheckEnvVar(debouncedUsernameEnv);
  const passwordEnvCheck = useCheckEnvVar(debouncedPasswordEnv);

  const startMutation = useStartDiscovery();
  const statusQuery = useDiscoveryStatus(submitted);
  const setTargetMutation = useSetTarget();

  const reset = () => {
    setStep(1);
    setName("");
    setBaseUrl("");
    setLoginPath("/login");
    setUsernameEnv("");
    setPasswordEnv("");
    setSubmitted(false);
  };

  const nameFormatError = name.length > 0 && !NAME_RE.test(name);
  const nameTaken =
    !nameFormatError && debouncedName === name && nameCheck.data?.available === false;
  const urlError = baseUrl.length > 0 && !URL_RE.test(baseUrl);
  const pathError = loginPath.length > 0 && !PATH_RE.test(loginPath);
  const usernameFormatError = usernameEnv.length > 0 && !ENV_NAME_RE.test(usernameEnv);
  const passwordFormatError = passwordEnv.length > 0 && !ENV_NAME_RE.test(passwordEnv);

  const canGoStep2 = name.trim().length > 0 && !nameFormatError && !nameTaken;
  const canGoStep3 = baseUrl.length > 0 && !urlError && loginPath.length > 0 && !pathError;
  const canSubmit =
    usernameEnv.length > 0 &&
    !usernameFormatError &&
    passwordEnv.length > 0 &&
    !passwordFormatError;

  const submit = () => {
    setSubmitted(true);
    startMutation.mutate(
      {
        name,
        base_url: baseUrl,
        login_path: loginPath,
        username_env: usernameEnv,
        password_env: passwordEnv,
      },
      {
        onError: (err) => {
          const detail =
            (err as ApiError)?.detail ??
            (err as Error)?.message ??
            t.discoverTargetDialog.unknownError;
          toast.error(t.discoverTargetDialog.couldNotStart(detail));
          setSubmitted(false);
        },
      },
    );
  };

  const status = statusQuery.data;
  const running = submitted && (startMutation.isPending || status?.running === true);
  const finished = submitted && !running && status != null && !status.running;

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (!o) reset();
      }}
    >
      <DialogTrigger asChild>
        <Button
          data-tour="add-target"
          variant="ghost"
          size="sm"
          className="gap-1.5 font-sans text-muted-foreground"
        >
          <CirclePlus className="h-4 w-4" />
          {t.discoverTargetDialog.triggerButton}
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{t.discoverTargetDialog.title}</DialogTitle>
        </DialogHeader>

        {!submitted && (
          <div className="space-y-4">
            <div className="space-y-1.5">
              <p className="text-xs font-semibold tracking-wider text-muted-foreground">
                {t.discoverTargetDialog.stepOf(step, 3)}
              </p>
              <StepProgress step={step} totalSteps={3} />
            </div>

            <h3 className="font-sans text-base font-medium text-foreground">
              {step === 1 && t.discoverTargetDialog.stepIdentity}
              {step === 2 && t.discoverTargetDialog.stepLocation}
              {step === 3 && t.discoverTargetDialog.stepCredentials}
            </h3>

            {step === 1 && (
              <div className="space-y-2">
                <Label htmlFor="discover-name">{t.discoverTargetDialog.nameLabel}</Label>
                <Input
                  id="discover-name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder={t.discoverTargetDialog.namePlaceholder}
                  autoFocus
                />
                {nameFormatError && (
                  <p className="text-xs text-destructive">{t.discoverTargetDialog.invalidName}</p>
                )}
                {!nameFormatError &&
                  name.trim() &&
                  debouncedName === name &&
                  nameCheck.isLoading && (
                    <p className="text-xs text-muted-foreground">
                      {t.discoverTargetDialog.nameChecking}
                    </p>
                  )}
                {nameTaken && (
                  <p className="text-xs text-destructive">{t.discoverTargetDialog.nameTaken}</p>
                )}
              </div>
            )}

            {step === 2 && (
              <div className="space-y-4">
                <p className="text-xs text-muted-foreground">
                  {t.discoverTargetDialog.baseUrlHelper}
                </p>
                <div className="space-y-2">
                  <Label htmlFor="discover-baseurl">{t.discoverTargetDialog.baseUrlLabel}</Label>
                  <Input
                    id="discover-baseurl"
                    value={baseUrl}
                    onChange={(e) => setBaseUrl(e.target.value)}
                    placeholder="http://localhost:3000"
                    autoFocus
                  />
                  {urlError && (
                    <p className="text-xs text-destructive">{t.discoverTargetDialog.invalidUrl}</p>
                  )}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="discover-loginpath">
                    {t.discoverTargetDialog.loginPathLabel}
                  </Label>
                  <Input
                    id="discover-loginpath"
                    value={loginPath}
                    onChange={(e) => setLoginPath(e.target.value)}
                    placeholder="/login"
                  />
                  {pathError && (
                    <p className="text-xs text-destructive">
                      {t.discoverTargetDialog.invalidLoginPath}
                    </p>
                  )}
                </div>
                {!urlError && !pathError && baseUrl && loginPath && (
                  <code className="block break-all rounded bg-muted px-2 py-1 text-xs">
                    {baseUrl}
                    {loginPath}
                  </code>
                )}
              </div>
            )}

            {step === 3 && (
              <div className="space-y-4">
                <p className="text-xs text-muted-foreground">
                  {t.discoverTargetDialog.credentialsHelper}
                </p>
                <EnvField
                  id="discover-usernameenv"
                  label={t.discoverTargetDialog.usernameEnvLabel}
                  value={usernameEnv}
                  onChange={setUsernameEnv}
                  formatError={usernameFormatError}
                  debouncedMatches={debouncedUsernameEnv === usernameEnv}
                  check={usernameEnvCheck}
                  t={t}
                />
                <EnvField
                  id="discover-passwordenv"
                  label={t.discoverTargetDialog.passwordEnvLabel}
                  value={passwordEnv}
                  onChange={setPasswordEnv}
                  formatError={passwordFormatError}
                  debouncedMatches={debouncedPasswordEnv === passwordEnv}
                  check={passwordEnvCheck}
                  t={t}
                />
              </div>
            )}

            <div className="flex justify-between pt-2">
              <Button
                variant="outline"
                size="sm"
                className="font-sans"
                onClick={() => (step === 1 ? setOpen(false) : setStep((s) => (s - 1) as Step))}
              >
                {step === 1 ? t.discoverTargetDialog.cancel : t.discoverTargetDialog.back}
              </Button>
              {step < 3 ? (
                <Button
                  size="sm"
                  className="font-sans"
                  disabled={step === 1 ? !canGoStep2 : !canGoStep3}
                  onClick={() => setStep((s) => (s + 1) as Step)}
                >
                  {t.discoverTargetDialog.next}
                </Button>
              ) : (
                <Button size="sm" className="font-sans" disabled={!canSubmit} onClick={submit}>
                  {t.discoverTargetDialog.startDiscovery}
                </Button>
              )}
            </div>
          </div>
        )}

        {submitted && running && (
          <div className="space-y-3">
            <div className="flex items-center gap-2 text-sm">
              <Loader2 className="h-4 w-4 animate-spin" />
              {t.discoverTargetDialog.runningTitle}
            </div>
            <p className="text-xs text-muted-foreground">{t.discoverTargetDialog.runningBody}</p>
          </div>
        )}

        {finished && (
          <ResultView
            name={name}
            result={status?.result ?? null}
            crashError={status?.error ?? null}
            onAddAnother={reset}
            onSwitchToIt={() =>
              setTargetMutation.mutate({ name }, { onSuccess: () => setOpen(false) })
            }
            onClose={() => setOpen(false)}
            t={t}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

function EnvField({
  id,
  label,
  value,
  onChange,
  formatError,
  debouncedMatches,
  check,
  t,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  formatError: boolean;
  debouncedMatches: boolean;
  check: ReturnType<typeof useCheckEnvVar>;
  t: Strings;
}) {
  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} value={value} onChange={(e) => onChange(e.target.value.toUpperCase())} />
      {formatError && (
        <p className="text-xs text-destructive">{t.discoverTargetDialog.invalidEnvVarName}</p>
      )}
      {!formatError && value.trim() && debouncedMatches && check.isLoading && (
        <p className="text-xs text-muted-foreground">{t.discoverTargetDialog.envVarChecking}</p>
      )}
      {!formatError && value.trim() && debouncedMatches && check.data && (
        <p
          className={
            "flex items-center gap-1 text-xs " +
            (check.data.present ? "text-primary" : "text-(--status-posible)")
          }
        >
          {check.data.present ? (
            <CheckCircle2 className="h-3.5 w-3.5" />
          ) : (
            <XCircle className="h-3.5 w-3.5" />
          )}
          {check.data.present
            ? t.discoverTargetDialog.envVarPresent
            : t.discoverTargetDialog.envVarMissing}
        </p>
      )}
    </div>
  );
}

function ResultView({
  name,
  result,
  crashError,
  onAddAnother,
  onSwitchToIt,
  onClose,
  t,
}: {
  name: string;
  result: DiscoveryResult | null;
  crashError: string | null;
  onAddAnother: () => void;
  onSwitchToIt: () => void;
  onClose: () => void;
  t: Strings;
}) {
  if (crashError && !result) {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-2 text-sm text-destructive">
          <XCircle className="h-5 w-5 shrink-0" />
          {t.discoverTargetDialog.couldNotStart(crashError)}
        </div>
        <div className="flex justify-end gap-2">
          <Button variant="outline" size="sm" className="font-sans" onClick={onAddAnother}>
            {t.discoverTargetDialog.addAnother}
          </Button>
          <Button size="sm" className="font-sans" onClick={onClose}>
            {t.discoverTargetDialog.close}
          </Button>
        </div>
      </div>
    );
  }

  if (!result) return null;

  const succeeded = result.login_succeeded;
  const allSelectors = [
    ...result.login_id_selectors,
    ...result.password_selectors,
    ...result.submit_selectors,
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        {succeeded ? (
          <CheckCircle2 className="h-5 w-5 shrink-0 text-primary" />
        ) : (
          <XCircle className="h-5 w-5 shrink-0 text-destructive" />
        )}
        <span className="text-sm font-semibold">{t.discoverTargetDialog.successTitle(name)}</span>
      </div>
      <p className="text-xs text-muted-foreground">
        {succeeded
          ? t.discoverTargetDialog.loginSucceeded
          : t.discoverTargetDialog.loginFailed(result.error ?? "")}
      </p>

      {allSelectors.length > 0 && (
        <div className="space-y-2">
          <label className="text-xs font-semibold tracking-wider text-muted-foreground">
            {t.discoverTargetDialog.selectorsFoundHeading}
          </label>
          <div className="flex flex-wrap gap-2">
            {allSelectors.map((s, i) => (
              <code key={i} className="rounded bg-muted px-2 py-1 text-xs">
                {s}
              </code>
            ))}
          </div>
        </div>
      )}

      <div className="flex flex-wrap justify-end gap-2 pt-2">
        <Button variant="outline" size="sm" className="font-sans" onClick={onAddAnother}>
          {t.discoverTargetDialog.addAnother}
        </Button>
        {succeeded ? (
          <Button size="sm" className="font-sans" onClick={onSwitchToIt}>
            {t.discoverTargetDialog.switchToIt}
          </Button>
        ) : (
          <Button size="sm" className="font-sans" onClick={onClose}>
            {t.discoverTargetDialog.close}
          </Button>
        )}
      </div>
    </div>
  );
}

/** One segment per step - segment i is lit once the user has reached step i
 * (so all segments are lit on the final step, not just totalSteps - 1 of them). */
function StepProgress({ step, totalSteps }: { step: number; totalSteps: number }) {
  const segments = Array.from({ length: totalSteps }, (_, i) => i + 1);
  return (
    <div className="flex gap-1.5">
      {segments.map((i) => (
        <div key={i} className="h-1 flex-1 overflow-hidden rounded-full bg-muted">
          <div
            className="h-full rounded-full bg-primary transition-all"
            style={{ width: step >= i ? "100%" : "0%" }}
          />
        </div>
      ))}
    </div>
  );
}
