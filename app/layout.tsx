import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000"),
  title: "RouteRecall — Agentic flight recovery that remembers",
  description: "A resilient flight-disruption recovery agent powered by CockroachDB persistent memory.",
  icons: { icon: "/favicon.svg", shortcut: "/favicon.svg" },
  openGraph: {
    title: "RouteRecall",
    description: "A cancelled flight. A recovery plan that remembers.",
    type: "website",
    images: [{ url: "/routerecall-social.png", width: 1728, height: 909, alt: "RouteRecall durable recovery agent" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "RouteRecall",
    description: "The recovery agent that remembers.",
    images: ["/routerecall-social.png"],
  },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className={`${geistSans.variable} ${geistMono.variable}`}>{children}</body>
    </html>
  );
}
