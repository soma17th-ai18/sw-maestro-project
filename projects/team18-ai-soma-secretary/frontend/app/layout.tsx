import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Soma Secretary",
  description: "Webex 기반 AI 일정 승인 콘솔"
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
