import "./globals.css";
import type { Metadata, Viewport } from "next";
import PwaRegister from "../components/PwaRegister";

const themeInit = `try{var t=localStorage.getItem('keel-theme');if(t){document.documentElement.dataset.theme=t;}}catch(e){}`;

export const metadata: Metadata = {
  title: "Keel Fleet",
  description: "Your agent workspace — named agents, notes, tasks and routines.",
  applicationName: "Keel Fleet",
  icons: {
    icon: [
      { url: "/icon.svg", type: "image/svg+xml" },
      { url: "/icon-192.png", sizes: "192x192", type: "image/png" },
    ],
    apple: "/icon-192.png",
  },
  appleWebApp: { capable: true, title: "Keel Fleet", statusBarStyle: "black-translucent" },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#e9e9e7" },
    { media: "(prefers-color-scheme: dark)", color: "#0a0605" },
  ],
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        {/* apply saved theme before first paint — no flash */}
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
