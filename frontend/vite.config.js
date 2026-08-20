import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "dist",
    cssCodeSplit: false,
    lib: {
      entry: "src/main.jsx",
      name: "SkapaChatbot",
      formats: ["iife"],
      fileName: () => "skapa-widget.js",
    },
  },
});
