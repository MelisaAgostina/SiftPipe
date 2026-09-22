import { createFileRoute, redirect } from "@tanstack/react-router";
import { SecPipelineApp } from "@/components/secpipeline/SecPipelineApp";
import { checkSession } from "@/lib/api";

export const Route = createFileRoute("/app")({
  beforeLoad: async () => {
    const authenticated = await checkSession();
    if (!authenticated) {
      throw redirect({ to: "/login" });
    }
  },
  component: () => <SecPipelineApp />,
});
