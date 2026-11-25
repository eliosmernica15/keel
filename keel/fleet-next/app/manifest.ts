import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Keel",
    short_name: "Keel",
    description:
      "A local-first AI workspace: Cowork, Code, Duet and Fleet in one coherent, offline-capable environment.",
    start_url: "/",
    display: "standalone",
    background_color: "#F7F4EF",
    theme_color: "#8A5A07",
    icons: [
      { src: "/icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any" },
      { src: "/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
    shortcuts: [
      {
        name: "Get Keel Desktop",
        short_name: "Get Desktop",
        description: "Download the Keel Desktop app for your platform.",
        url: "https://keel-desktop.vercel.app/download",
      },
    ],
  };
}
