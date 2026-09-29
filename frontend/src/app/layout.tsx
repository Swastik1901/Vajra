import "./globals.css";
import "maplibre-gl/dist/maplibre-gl.css";
import type { ReactNode } from "react";

export const metadata = {
  title: "Convective storm nowcasting · 0–6 h",
  description: "Live hyper-local thunderstorm, hail, downburst and cloudburst risk",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
