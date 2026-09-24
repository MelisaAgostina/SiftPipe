import * as DialogPrimitive from "@radix-ui/react-dialog";
import { useLang } from "@/hooks/use-lang";
import { Dialog, DialogOverlay, DialogPortal } from "@/components/ui/dialog";
import guidedTourCat from "@/assets/guidedtour-cat.svg";

/**
 * First-visit welcome card offering the guided tour. Purely presentational: the
 * "is this a first visit" decision and the remembered choice live in
 * SecPipelineApp. Built from the Radix primitives instead of ui/dialog's
 * DialogContent because that always draws an "X" button, and the design has
 * Skip as the one way out. Esc and clicking outside also count as Skip, so the
 * card can never trap someone.
 */
export function WelcomeCard({
  open,
  onSkip,
  onStart,
}: {
  open: boolean;
  onSkip: () => void;
  onStart: () => void;
}) {
  const { t } = useLang();

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onSkip()}>
      <DialogPortal>
        <DialogOverlay />
        <DialogPrimitive.Content className="fixed left-1/2 top-1/2 z-50 flex w-[min(90vw,34rem)] -translate-x-1/2 -translate-y-1/2 flex-col items-center gap-3 rounded-3xl bg-[#004aad] px-8 pb-6 pt-8 text-center text-white shadow-2xl duration-200 data-[state=closed]:animate-out data-[state=open]:animate-in data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95">
          <DialogPrimitive.Title className="text-5xl font-semibold tracking-tight">
            {t.welcomeCard.title}
          </DialogPrimitive.Title>
          <img src={guidedTourCat} alt="" aria-hidden="true" className="h-28 w-auto" />
          <p className="text-2xl font-medium">{t.welcomeCard.question}</p>
          <DialogPrimitive.Description className="max-w-xs text-balance text-base leading-snug">
            {t.welcomeCard.description}
          </DialogPrimitive.Description>
          <div className="mt-4 flex w-full justify-end gap-3">
            <button
              type="button"
              onClick={onSkip}
              className="cursor-pointer rounded-full bg-[#b3b3b3] px-9 py-3 text-lg font-medium text-[#555] transition-colors hover:bg-[#c4c4c4] focus:outline-none focus-visible:ring-2 focus-visible:ring-white"
            >
              {t.welcomeCard.skip}
            </button>
            <button
              type="button"
              onClick={onStart}
              className="cursor-pointer rounded-full bg-[#00c160] px-9 py-3 text-lg font-medium text-white transition-colors hover:bg-[#00d46a] focus:outline-none focus-visible:ring-2 focus-visible:ring-white"
            >
              {t.welcomeCard.start}
            </button>
          </div>
        </DialogPrimitive.Content>
      </DialogPortal>
    </Dialog>
  );
}
