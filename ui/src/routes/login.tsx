import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { LoginPage } from "@/components/auth/LoginPage";

export const Route = createFileRoute("/login")({
  component: LoginRoute,
});

function LoginRoute() {
  const navigate = useNavigate();
  return <LoginPage onAuthenticated={() => navigate({ to: "/app" })} />;
}
