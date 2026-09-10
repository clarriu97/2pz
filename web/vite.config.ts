import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}", "functions/**/*.test.js"],
    coverage: {
      provider: "v8",
      reporter: ["text", "json-summary", "lcov"],
      include: ["src/**/*.{ts,tsx}", "functions/**/*.js"],
      // The map component is a thin imperative wrapper over MapLibre's canvas
      // API, which jsdom cannot render; testing it here would assert our mocks
      // rather than the map. It is verified by hand in the browser instead.
      exclude: ["src/main.tsx", "src/types.ts", "src/components/MapView.tsx", "src/test/**"],
      thresholds: {
        lines: 85,
        functions: 85,
        branches: 80,
        statements: 85,
      },
    },
  },
});
