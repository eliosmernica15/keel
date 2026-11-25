import type { Page } from "@playwright/test";

export const SHA_A = "a".repeat(64);
export const SHA_B = "b".repeat(64);
// First-party release host approved by site/ui/download.js's host allowlist.
export const PRIMARY_URL = "https://github.com/keel-org/keel/releases/download/v9.9.9/Keel-Setup-9.9.9.exe";

export type Channel = {
  name?: string;
  arch?: string;
  version?: string;
  file?: string;
  size?: number | null;
  sha256?: string | null;
  url?: string | null;
  available?: boolean;
  verified?: boolean;
  verified_at?: string | null;
  notes?: string;
  installation?: string;
  alternatives?: Array<Record<string, unknown>>;
};

export type Manifest = {
  name?: string;
  version: string;
  tag?: string;
  generated?: string;
  channels: Record<string, Channel>;
};

const unavailable = (name: string, arch: string, file: string): Channel => ({
  name,
  arch,
  version: "9.9.9",
  file,
  size: null,
  sha256: null,
  url: null,
  available: false,
  verified: false,
  verified_at: null,
  notes: "Not publicly hosted yet; there is nothing to download.",
  alternatives: [],
});

export const fallbackManifest: Manifest = {
  name: "Keel Desktop",
  version: "9.9.9",
  channels: {
    windows: unavailable("Windows x64 (64-bit)", "x64", "Keel-Setup-9.9.9.exe"),
    macos: {
      ...unavailable("macOS arm64 (Apple Silicon)", "arm64", "Keel-9.9.9-macos-arm64.dmg"),
      alternatives: [
        { label: "Intel", arch: "x64", file: "Keel-9.9.9-macos-x64.dmg", available: false },
        { label: "Apple Silicon ZIP", arch: "arm64", file: "Keel-9.9.9-macos-arm64.zip", available: false },
      ],
    },
    linux: {
      ...unavailable("Linux x86_64", "x86_64", "Keel-9.9.9-linux-x86_64.AppImage"),
      alternatives: [
        { label: "DEB", arch: "x86_64", file: "Keel-9.9.9-linux-amd64.deb", available: false },
        { label: "RPM", arch: "x86_64", file: "Keel-9.9.9-linux-x86_64.rpm", available: false },
      ],
    },
  },
};

export const availableManifest: Manifest = {
  ...fallbackManifest,
  channels: {
    ...fallbackManifest.channels,
    windows: {
      ...fallbackManifest.channels.windows,
      size: 12345678,
      sha256: SHA_A,
      url: PRIMARY_URL,
      available: true,
      verified: true,
      verified_at: "2026-11-25T00:00:00Z",
    },
  },
};

/** Every "available" flag is true but the asset fails the honesty gate. */
export const dishonestManifest: Manifest = {
  ...fallbackManifest,
  channels: {
    windows: {
      ...fallbackManifest.channels.windows,
      available: true,
      verified: true,
      size: 0,
      sha256: "short",
      url: "http://example.invalid/Keel-Setup.exe",
    },
    macos: {
      ...fallbackManifest.channels.macos,
      available: true,
      verified: false,
      size: 200,
      sha256: SHA_B,
      url: "https://example.invalid/Keel.dmg",
    },
    linux: { ...fallbackManifest.channels.linux, available: true, verified: true, url: null },
  },
};

/** Serve a manifest through the same two URLs the page really fetches. */
export async function mockManifest(
  page: Page,
  opts: {
    api?: Manifest | null;
    apiStatus?: number;
    fallback?: Manifest | null;
    fallbackStatus?: number;
  } = {}
) {
  const api = opts.api === undefined ? fallbackManifest : opts.api;
  const fallback = opts.fallback === undefined ? fallbackManifest : opts.fallback;
  await page.route("**/api/download-manifest", (route) =>
    api === null
      ? route.fulfill({ status: opts.apiStatus ?? 503, contentType: "application/json", body: JSON.stringify({ error: "manifest_not_configured" }) })
      : route.fulfill({ status: opts.apiStatus ?? 200, contentType: "application/json", body: JSON.stringify(api) })
  );
  await page.route("**/download.json", (route) =>
    fallback === null
      ? route.fulfill({ status: opts.fallbackStatus ?? 404, contentType: "application/json", body: "{}" })
      : route.fulfill({ status: opts.fallbackStatus ?? 200, contentType: "application/json", body: JSON.stringify(fallback) })
  );
}

export type PlatformCase = {
  name: string;
  userAgent: string;
  platform: string;
  uaPlatform: string;
  architecture: string;
  bitness: string;
};

export const PLATFORMS: PlatformCase[] = [
  {
    name: "windows-x64",
    userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    platform: "Win32",
    uaPlatform: "Windows",
    architecture: "x86",
    bitness: "64",
  },
  {
    name: "windows-arm64",
    userAgent: "Mozilla/5.0 (Windows NT 10.0; ARM64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    platform: "Win32",
    uaPlatform: "Windows",
    architecture: "arm",
    bitness: "64",
  },
  {
    name: "macos-arm64",
    userAgent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    platform: "MacIntel",
    uaPlatform: "macOS",
    architecture: "arm",
    bitness: "64",
  },
  {
    name: "macos-x64",
    userAgent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    platform: "MacIntel",
    uaPlatform: "macOS",
    architecture: "x86",
    bitness: "64",
  },
  {
    name: "linux-x64",
    userAgent: "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    platform: "Linux x86_64",
    uaPlatform: "Linux",
    architecture: "x86",
    bitness: "64",
  },
  {
    name: "ios",
    userAgent: "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17.0 Mobile Safari/604.1",
    platform: "iPhone",
    uaPlatform: "iOS",
    architecture: "arm",
    bitness: "64",
  },
  {
    name: "android",
    userAgent: "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/131.0.0.0 Mobile Safari/537.36",
    platform: "Linux armv8l",
    uaPlatform: "Android",
    architecture: "arm",
    bitness: "64",
  },
];
