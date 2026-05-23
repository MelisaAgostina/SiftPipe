import { Section } from "./Section";
import { correlationSections } from "./data";

function Stat({ value, label, tone }: { value: string; label: string; tone: "ok" | "neutral" | "info" }) {
  const color =
    tone === "ok" ? "text-primary" : tone === "info" ? "text-[var(--status-form)]" : "text-foreground";
  return (
    <div className="rounded-lg border border-border bg-card px-6 py-5 text-center">
      <div className={"text-3xl font-semibold " + color}>{value}</div>
      <div className="mt-1 text-xs text-muted-foreground">{label}</div>
    </div>
  );
}

export function CorrelationView() {
  return (
    <div className="space-y-6">
      {correlationSections.map((s) => (
        <Section key={s.id} section={s} />
      ))}

      <section className="space-y-3">
        <h3 className="text-xs font-semibold tracking-wider text-muted-foreground">
          B9 — CORRELACIÓN ESTÁTICO + DINÁMICO · NÚCLEO DEL HÍBRIDO
        </h3>
        <div className="grid gap-3 md:grid-cols-2">
          <div className="rounded-lg border border-border bg-card p-4">
            <p className="text-xs text-muted-foreground">Estático detectó</p>
            <p className="mt-1 text-sm font-medium text-foreground">SQLi en auth.go:42</p>
            <p className="text-xs text-muted-foreground">confianza: alta</p>
          </div>
          <div className="rounded-lg border border-border bg-card p-4">
            <p className="text-xs text-muted-foreground">Dinámico confirmó</p>
            <p className="mt-1 text-sm font-medium text-foreground">payload ejecutado en login_form</p>
            <p className="text-xs text-muted-foreground">DB error visible en response</p>
          </div>
        </div>
        <div className="rounded-lg border border-primary/40 bg-primary/10 p-4 text-sm text-foreground">
          <p className="font-semibold text-primary">
            Resultado: VULNERABILIDAD CONFIRMADA · SQL Injection · confianza muy alta
          </p>
          <p className="mt-1 text-xs text-muted-foreground">(ambas fuentes coinciden)</p>
        </div>
      </section>

      <div className="grid gap-4 md:grid-cols-3">
        <Stat value="9/9" label="confirmadas" tone="ok" />
        <Stat value="0" label="falsos positivos" tone="neutral" />
        <Stat value="55 min" label="tiempo total" tone="info" />
      </div>
    </div>
  );
}
