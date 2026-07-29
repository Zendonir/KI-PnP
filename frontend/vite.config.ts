import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";

// Die App laeuft als installierbare PWA auf iPhone und Android.
// Im Entwicklungsmodus werden API und WebSocket an das Backend
// weitergereicht, im Betrieb uebernimmt das der Reverse Proxy.
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["favicon.svg"],
      manifest: {
        name: "KI-PnP - Pen & Paper mit KI-Spielleiter",
        short_name: "KI-PnP",
        description:
          "Mehrere Spieler, ein KI-Spielleiter, eine dauerhaft gespeicherte Welt.",
        lang: "de",
        start_url: "/",
        display: "standalone",
        orientation: "portrait",
        background_color: "#0b0b12",
        theme_color: "#0b0b12",
        icons: [
          { src: "/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
          { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
          { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
        ],
      },
      workbox: {
        // API-Antworten nie cachen - der Spielzustand kommt immer frisch.
        navigateFallbackDenylist: [/^\/api/],
        globPatterns: ["**/*.{js,css,html,svg,png,woff2}"],
      },
    }),
  ],
  server: {
    host: true,
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.VITE_DEV_BACKEND ?? "http://localhost:8000",
        changeOrigin: true,
        ws: true,
      },
    },
  },
  // `vite preview` dient zum Pruefen des Produktions-Builds ohne Docker.
  preview: {
    host: true,
    port: 4173,
    proxy: {
      "/api": {
        target: process.env.VITE_DEV_BACKEND ?? "http://localhost:8000",
        changeOrigin: true,
        ws: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
});
