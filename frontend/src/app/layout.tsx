import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import LanguageSelector from "@/components/LanguageSelector";
import SiteFooter from "@/components/SiteFooter";
import { I18nProvider } from "@/lib/i18n";
import { rootMetadata } from "@/lib/seo";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = rootMetadata();

export const viewport: Viewport = {
  themeColor: "#18181b",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <I18nProvider>
          <LanguageSelector />
          {children}
          <SiteFooter />
        </I18nProvider>
      </body>
    </html>
  );
}
