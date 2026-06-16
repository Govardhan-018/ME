import type { Metadata, Viewport } from "next";
import { Inter, Inter_Tight, JetBrains_Mono } from "next/font/google";
import "./globals.css";
// EXPERIMENTAL — Liquid Glass. Remove this import + <LiquidGlass/> below + the
// data-lg attr on <html> to fully revert. See app/liquid-glass.css header.
import { LiquidGlass } from "@/components/ui/LiquidGlass";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });
const interTight = Inter_Tight({
  subsets: ["latin"],
  variable: "--font-inter-tight",
  display: "swap",
});
const jetbrains = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains",
  display: "swap",
});

export const metadata: Metadata = {
  title: "JARVIS",
  description: "Personal intelligence operating system.",
  robots: { index: false, follow: false },
};

export const viewport: Viewport = {
  themeColor: "#050507",
  colorScheme: "dark",
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" data-lg="on" suppressHydrationWarning className={`${inter.variable} ${interTight.variable} ${jetbrains.variable}`}>
      <body suppressHydrationWarning className="bg-void text-ink antialiased">
        {children}
        <LiquidGlass />
      </body>
    </html>
  );
}
