import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    chunkSizeWarningLimit: 950,
    rollupOptions: {
      output: {
        manualChunks: {
          "gltf-runtime": [
            "three/examples/jsm/loaders/GLTFLoader.js",
            "three/examples/jsm/utils/SkeletonUtils.js",
          ],
        },
      },
    },
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
  },
});
