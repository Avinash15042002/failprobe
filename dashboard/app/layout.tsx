import type { Metadata } from "next";

import { Sidebar } from "@/components/sidebar";
import { Topbar } from "@/components/topbar";

import "./globals.css";

export const metadata: Metadata = {
  title: "AgentProbe",
  description: "LLM agent failure classifier, meta-evaluator, and regression CI.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="antialiased">
        <div className="flex h-screen overflow-hidden">
          <Sidebar />
          <div className="flex flex-1 flex-col overflow-hidden">
            <Topbar />
            <main className="flex-1 overflow-auto p-6">{children}</main>
          </div>
        </div>
      </body>
    </html>
  );
}
