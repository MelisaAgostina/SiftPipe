import { Callout } from "./Callout";
import { Section } from "./Section";
import { pipelineSections } from "./data";

export function PipelineView() {
  return (
    <div className="space-y-6">
      <Callout>
        Lo que ves acá es el pipeline corriendo sobre Mattermost en vivo. El experimento que
        valida este enfoque está documentado por separado.
      </Callout>
      {pipelineSections.map((s) => (
        <Section key={s.id} section={s} />
      ))}
    </div>
  );
}
