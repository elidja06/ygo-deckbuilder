import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "VS Deckbuilder",
  description: "Deckbuilder Yu-Gi-Oh! avec moteur de combos et suggestions",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="fr" className="h-full antialiased">
      <body className="min-h-full">{children}</body>
    </html>
  );
}
