import type { Metadata } from "next";
import Link from "next/link";
import { Geist, Geist_Mono } from "next/font/google";
import { History, Plus } from "lucide-react";
import { BackendBanner, BackendPill } from "@/components/BackendStatus";
import { Logo } from "@/components/Brand";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Scout — source-backed data from plain English",
  description: "Describe the data you need. Scout builds the workflow, collects from permitted sources, and proves every value with a quote.",
};

function GitHubIcon() {
  return (
    <svg viewBox="0 0 16 16" className="size-4" fill="currentColor" aria-hidden="true">
      <path d="M8 0a8 8 0 0 0-2.53 15.59c.4.07.55-.17.55-.38v-1.33c-2.23.48-2.7-1.07-2.7-1.07-.36-.92-.89-1.17-.89-1.17-.73-.5.05-.49.05-.49.8.06 1.23.83 1.23.83.72 1.23 1.88.87 2.34.67.07-.52.28-.87.5-1.07-1.78-.2-3.65-.89-3.65-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.22 2.2.82a7.6 7.6 0 0 1 4 0c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.28.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48v2.2c0 .21.15.46.55.38A8 8 0 0 0 8 0Z" />
    </svg>
  );
}

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased min-h-screen app-backdrop`}>
        <header className="sticky top-0 z-30 border-b border-line bg-panel/75 backdrop-blur-md">
          <div className="mx-auto flex h-14 max-w-7xl items-center gap-6 px-4">
            <Link href="/" className="flex items-center gap-2.5">
              <Logo />
              <span className="text-[17px] font-semibold tracking-tight">Scout</span>
            </Link>
            <nav className="flex gap-1 text-sm">
              <Link href="/" className="inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-muted hover:bg-panel-2 hover:text-fg">
                <Plus className="size-4" /> New
              </Link>
              <Link href="/runs" className="inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-muted hover:bg-panel-2 hover:text-fg">
                <History className="size-4" /> Runs
              </Link>
            </nav>
            <div className="ml-auto flex items-center gap-2">
              <BackendPill />
              <a
                href="https://github.com/geekksv/scout"
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 rounded-md border border-line bg-panel px-2.5 py-1 text-xs text-muted hover:text-fg"
              >
                <GitHubIcon /> <span className="hidden sm:inline">GitHub</span>
              </a>
            </div>
          </div>
          <BackendBanner />
        </header>
        <main className="mx-auto max-w-7xl px-4 py-6">{children}</main>
        <footer className="mx-auto max-w-7xl px-4 pb-8 pt-4 text-xs text-muted">
          Scout · every value backed by a verbatim quote from a permitted source · robots.txt respected
        </footer>
      </body>
    </html>
  );
}
