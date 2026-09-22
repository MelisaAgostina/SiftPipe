import { useEffect, useRef, useState, type FormEvent } from "react";
import { ApiError, login } from "@/lib/api";
import { useLang } from "@/hooks/use-lang";
import "./LoginPage.css";

const COUNTDOWN_SECONDS = 5;

interface LoginPageProps {
  /** Called once the post-success countdown finishes. The actual /app
   * navigation is the caller's job (see routes/login.tsx) - this component
   * stays router-agnostic so it can be unit-tested without a router
   * context. */
  onAuthenticated: () => void;
}

export function LoginPage({ onAuthenticated }: LoginPageProps) {
  const { t } = useLang();
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [countdown, setCountdown] = useState(COUNTDOWN_SECONDS);
  const [formWidth, setFormWidth] = useState<number | undefined>(undefined);
  const inputRef = useRef<HTMLInputElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // Keep the input/button exactly as wide as the rendered title.
  useEffect(() => {
    const measure = () => {
      if (titleRef.current) setFormWidth(titleRef.current.getBoundingClientRect().width);
    };
    measure();

    if (typeof document !== "undefined" && "fonts" in document) {
      document.fonts.ready.then(measure).catch(() => {});
    }

    const ro = new ResizeObserver(measure);
    if (titleRef.current) ro.observe(titleRef.current);
    window.addEventListener("resize", measure);
    return () => {
      ro.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, []);

  useEffect(() => {
    if (!success) return;
    if (countdown <= 0) {
      onAuthenticated();
      return;
    }
    const timer = setTimeout(() => setCountdown((c) => c - 1), 1000);
    return () => clearTimeout(timer);
  }, [success, countdown, onAuthenticated]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (loading || success) return;
    setError(null);
    setLoading(true);

    try {
      await login(password);
      setSuccess(true);
    } catch (err) {
      if (err instanceof ApiError && err.status === 429) {
        setError(t.login.errorTooManyAttempts);
      } else if (err instanceof ApiError && err.status >= 500) {
        setError(t.login.errorServer);
      } else if (err instanceof ApiError) {
        setError(t.login.errorWrongPassword);
      } else {
        setError(t.login.errorNetwork);
      }
      setPassword("");
      inputRef.current?.focus();
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="pp-page">
      <link
        rel="stylesheet"
        href="https://fonts.googleapis.com/css2?family=Bitcount+Prop+Single:wght@100..900&family=Outfit:wght@100..900&family=Playfair+Display:ital,wght@0,400..900;1,400..900&family=Press+Start+2P&display=swap"
      />

      <main className="pp-card" role="main">
        <h1 className="pp-title" ref={titleRef}>
          {t.login.title}
        </h1>

        {!success ? (
          <>
            <p className="pp-subtitle">{t.login.subtitle}</p>

            <form
              onSubmit={handleSubmit}
              noValidate
              className="pp-form"
              style={{ maxWidth: formWidth }}
            >
              <div className="pp-field">
                <input
                  ref={inputRef}
                  type={showPassword ? "text" : "password"}
                  name="password"
                  autoComplete="current-password"
                  placeholder={t.login.passwordPlaceholder}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  aria-label={t.login.passwordAriaLabel}
                  aria-invalid={!!error}
                  disabled={loading}
                  className="pp-input"
                />
                <button
                  type="button"
                  className="pp-reveal"
                  onClick={() => setShowPassword((s) => !s)}
                  aria-label={showPassword ? t.login.hidePassword : t.login.showPassword}
                  tabIndex={-1}
                >
                  {showPassword ? <EyeOpenIcon /> : <EyeClosedIcon />}
                </button>
              </div>

              <p className="pp-error" role="alert" aria-live="polite">
                {error || " "}
              </p>

              <button type="submit" className="pp-submit" disabled={loading}>
                {loading ? t.login.checking : t.login.submit}
              </button>
            </form>
          </>
        ) : (
          <div className="pp-success" aria-live="polite">
            <p className="pp-successTitle">{t.login.successTitle}</p>
            <p className="pp-subtitle">{t.login.successSubtitle(countdown)}</p>
          </div>
        )}
      </main>
    </div>
  );
}

// Both paths below are traced directly from the user-supplied icon artwork
// (Noun Project cat-face eye/eye-slash pair) with potrace, background and
// attribution text removed. Same viewBox/transform for both so they align.
const ICON_VIEWBOX = "0 0 635 515";
const ICON_TRANSFORM = "translate(0,515) scale(0.1,-0.1)";

const EYE_OPEN_PATH =
  "M580 4164 l0 -785 -38 -52 c-67 -90 -119 -179 -176 -297 -196 -408 -216 -836 -60 -1257 191 -518 677 -982 1324 -1266 855 -375 1929 -415 2829 -105 879 303 1489 881 1656 1570 83 343 43 707 -115 1043 -49 106 -130 242 -183 309 l-32 40 -5 791 -5 792 -970 -267 -970 -267 -85 13 c-325 47 -815 47 -1140 0 l-85 -13 -905 249 c-498 137 -935 257 -972 267 l-68 19 0 -784z m1126 156 l802 -221 137 20 c332 49 738 49 1070 0 l137 -20 802 221 c441 121 805 220 809 220 4 0 7 -286 7 -636 l0 -635 54 -67 c152 -189 263 -423 307 -647 21 -104 18 -369 -4 -473 -55 -250 -172 -480 -349 -682 -422 -482 -1108 -796 -1928 -882 -183 -19 -610 -16 -790 6 -621 75 -1141 267 -1559 578 -127 95 -339 309 -423 428 -118 166 -204 361 -245 550 -25 117 -25 382 0 497 49 228 152 442 305 632 l52 64 0 634 c0 348 3 633 7 633 4 0 368 -99 809 -220z M1640 3035 c-235 -40 -463 -136 -696 -294 -185 -125 -191 -132 -205 -221 -43 -282 101 -639 357 -881 169 -159 388 -270 614 -310 102 -18 295 -16 403 5 313 60 604 248 769 496 84 126 150 310 135 372 -11 42 -141 229 -240 343 -333 387 -733 559 -1137 490z m143 -382 c-76 -287 -76 -678 1 -944 l23 -79 -26 0 c-37 0 -159 35 -226 65 -262 116 -490 416 -512 673 l-6 68 89 59 c211 141 471 241 635 244 l46 1 -24 -87z m253 56 c150 -46 279 -132 434 -288 63 -64 141 -153 173 -198 l58 -82 -20 -47 c-77 -173 -267 -337 -488 -420 -58 -22 -232 -59 -239 -51 -2 2 7 48 21 102 14 54 32 153 41 219 31 236 1 605 -62 771 -8 20 1 19 82 -6z M4363 3036 c-320 -61 -621 -270 -877 -609 -35 -47 -83 -117 -106 -156 -40 -67 -42 -75 -36 -122 34 -256 282 -557 581 -707 281 -140 617 -165 904 -67 496 168 862 704 790 1155 -12 78 -23 89 -204 212 -196 133 -436 240 -635 283 -104 22 -326 28 -417 11z m323 -306 c162 -29 375 -120 547 -234 86 -58 87 -59 87 -100 0 -22 -7 -69 -15 -104 -58 -247 -264 -493 -500 -597 -67 -30 -189 -65 -226 -65 l-26 0 23 79 c76 264 77 658 1 944 l-24 87 37 0 c20 0 63 -5 96 -10z m-280 -15 c-38 -100 -67 -284 -73 -470 -6 -194 11 -370 53 -525 13 -51 23 -95 21 -97 -8 -8 -181 29 -240 51 -221 83 -411 247 -488 420 l-20 47 58 81 c32 44 100 125 151 179 147 155 295 256 445 305 86 28 101 29 93 9z";

const EYE_CLOSED_PATH =
  "M580 4164 l0 -785 -38 -52 c-67 -90 -119 -179 -176 -297 -196 -408 -216 -836 -60 -1257 191 -518 677 -982 1324 -1266 855 -375 1929 -415 2829 -105 879 303 1489 881 1656 1570 83 343 43 707 -115 1043 -49 106 -130 242 -183 309 l-32 40 -5 791 -5 792 -970 -267 -970 -267 -85 13 c-325 47 -815 47 -1140 0 l-85 -13 -905 249 c-498 137 -935 257 -972 267 l-68 19 0 -784z m1126 156 l802 -221 137 20 c332 49 738 49 1070 0 l137 -20 802 221 c441 121 805 220 809 220 4 0 7 -286 7 -636 l0 -635 54 -67 c152 -189 263 -423 307 -647 21 -104 18 -369 -4 -473 -55 -250 -172 -480 -349 -682 -422 -482 -1108 -796 -1928 -882 -183 -19 -610 -16 -790 6 -621 75 -1141 267 -1559 578 -127 95 -339 309 -423 428 -118 166 -204 361 -245 550 -25 117 -25 382 0 497 49 228 152 442 305 632 l52 64 0 634 c0 348 3 633 7 633 4 0 368 -99 809 -220z M773 2574 c-62 -47 -113 -90 -113 -96 0 -30 231 -281 349 -379 303 -254 597 -369 939 -369 222 0 399 38 605 130 100 45 243 127 304 176 l26 21 -98 117 -98 117 -26 -18 c-82 -55 -190 -115 -254 -142 -250 -104 -495 -124 -729 -60 -110 30 -284 119 -395 203 -98 74 -277 251 -343 338 -19 26 -39 47 -45 48 -5 0 -61 -39 -122 -86z M5395 2574 c-224 -276 -497 -458 -777 -520 -101 -23 -309 -22 -413 0 -159 35 -339 111 -467 197 l-57 39 -58 -68 c-127 -147 -136 -161 -123 -177 40 -48 291 -184 430 -233 191 -67 255 -77 485 -76 202 0 214 1 325 31 267 71 487 201 709 417 97 94 261 281 261 296 0 9 -226 180 -237 180 -5 0 -39 -39 -78 -86z";

/** Cat face, eyes open — click to reveal the password. Traced from the user's icon. */
function EyeOpenIcon() {
  return (
    <svg width="32" height="26" viewBox={ICON_VIEWBOX} fill="currentColor" aria-hidden="true">
      <g transform={ICON_TRANSFORM}>
        <path d={EYE_OPEN_PATH} />
      </g>
    </svg>
  );
}

/** Cat face, eyes closed — click to hide the password again. Traced from the user's icon. */
function EyeClosedIcon() {
  return (
    <svg width="32" height="26" viewBox={ICON_VIEWBOX} fill="currentColor" aria-hidden="true">
      <g transform={ICON_TRANSFORM}>
        <path d={EYE_CLOSED_PATH} />
      </g>
    </svg>
  );
}
