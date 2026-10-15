import { AuthProvider } from "@/auth/AuthContext";
import Component from "@/components/ui/modern-login-signup";

// Live preview of the login/signup component. It talks to the real auth API, so it sits inside the AuthProvider.
export default function DemoOne() {
  return (
    <AuthProvider>
      <Component />
    </AuthProvider>
  );
}
