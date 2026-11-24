import "./globals.css";
import "./ui.css";
import type { Metadata, Viewport } from "next";
import PwaRegister from "../components/PwaRegister";

// Apply the saved theme synchronously before first paint — no flash.
// Preferences are stored as JSON by lib/state.tsx; fall back to system scheme.
const themeInit = `
try{
  var raw=localStorage.getItem('keel-theme-v2');
  var t=raw?JSON.parse(raw):null;
  if(t==='system'||!t){t=window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';}
  if(t){document.documentElement.dataset.theme=t;}
  if(window.matchMedia('(prefers-reduced-motion: reduce)').matches){document.documentElement.dataset.reducedMotion='true';}
}catch(e){}
`;

export const metadata: Metadata = {
  title: "Keel — Unified Workspace",
  description: "Keel is a local-first AI work environment: Cowork, Code, Duet and Fleet in one coherent workspace.",
  applicationName: "Keel",
  icons: {
    icon: [
      { url: "/icon.svg", type: "image/svg+xml" },
      { url: "/icon-192.png", sizes: "192x192", type: "image/png" },
    ],
    apple: "/icon-192.png",
  },
  appleWebApp: { capable: true, title: "Keel", statusBarStyle: "black-translucent" },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#F7F4EF" },
    { media: "(prefers-color-scheme: dark)", color: "#0A0605" },
  ],
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInit }} />
        <link rel="manifest" href="/manifest.webmanifest" />
      </head>
      <body>
        {children}
        <PwaRegister />
      </body>
    </html>
  );
}
