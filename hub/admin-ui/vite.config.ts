import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "../src/ina_device_hub/static/admin-layout",
    emptyOutDir: true,
    cssCodeSplit: false,
    rollupOptions: {
      input: "src/main.tsx",
      output: {
        entryFileNames: "installation-layout.js",
        chunkFileNames: "assets/[name]-[hash].js",
        assetFileNames: (assetInfo) =>
          assetInfo.name?.endsWith(".css") ? "installation-layout.css" : "assets/[name]-[hash][extname]",
        manualChunks: (id) => {
          if (id.includes("node_modules/konva") || id.includes("node_modules/react-konva")) return "canvas";
          if (id.includes("node_modules/lucide-react")) return "icons";
          if (id.includes("node_modules/react/") || id.includes("node_modules/react-dom/")) return "react";
          return undefined;
        },
      },
    },
  },
});
