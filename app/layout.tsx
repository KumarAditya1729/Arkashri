import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { AuthGuard } from "@/components/auth/AuthGuard";
import { WebSocketProvider } from "@/components/providers/WebSocketProvider";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

export const metadata: Metadata = {
  title: "Arkashri | Universal Audit",
  description: "Enterprise-Grade Universal Audit Command Surface",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${inter.variable} font-sans antialiased text-slate-900 bg-gray-50`}>
        <AuthGuard>
          <WebSocketProvider>
            {children}
          </WebSocketProvider>
        </AuthGuard>
      </body>
    </html>
  );
}

