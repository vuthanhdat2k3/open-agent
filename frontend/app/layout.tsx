"use client";

import "./globals.css";
import * as React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "sonner";
import { Inter, JetBrains_Mono } from "next/font/google";
import { usePathname } from "next/navigation";
import { getAccessToken, refreshAccessToken, subscribeAuth } from "@/lib/auth";
import { AppShell } from "@/components/layout/app-shell";

const sans = Inter({
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700"],
  variable: "--font-sans",
  display: "swap",
});
const mono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-mono",
  display: "swap",
});

function AuthGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [ready, setReady] = React.useState(false);
  const publicRoute = pathname === "/login" || pathname === "/register" || pathname.startsWith("/oauth/");

  React.useEffect(() => {
    const unsubscribe = subscribeAuth(() => setReady(true));
    if (getAccessToken() || publicRoute) {
      setReady(true);
      return unsubscribe;
    }
    setReady(false);
    refreshAccessToken().finally(() => setReady(true));
    return unsubscribe;
  }, [publicRoute, pathname]);

  React.useEffect(() => {
    if (ready && !publicRoute && !getAccessToken()) window.location.replace("/login");
  }, [ready, publicRoute, pathname]);

  if (!ready && !publicRoute) return <div className="p-6 text-sm text-muted-foreground">Preparing session...</div>;
  return <>{children}</>;
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const [client] = React.useState(() => new QueryClient({
    defaultOptions: {
      queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 30_000, gcTime: 10 * 60_000 },
    },
  }));
  const pathname = usePathname();
  const isPublic = pathname === "/login" || pathname === "/register" || pathname.startsWith("/oauth/");

  return (
    <html lang="en" className={`${sans.variable} ${mono.variable} dark`}>
      <head><link rel="icon" href="/openagent-icon.png" type="image/png" /></head>
      <body className="min-h-dvh bg-background font-sans text-foreground antialiased">
        <QueryClientProvider client={client}>
          <AuthGate>
            {isPublic ? <main className="min-h-dvh">{children}</main> : <AppShell queryClient={client}>{children}</AppShell>}
          </AuthGate>
          <Toaster richColors closeButton position="bottom-right" />
        </QueryClientProvider>
      </body>
    </html>
  );
}
