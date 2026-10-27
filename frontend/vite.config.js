import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In dev, proxy API calls to the FastAPI server on :8000.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/upload": "http://localhost:8000",
      "/ask": "http://localhost:8000",
    },
  },
});
