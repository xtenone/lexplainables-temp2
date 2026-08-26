// Flat ESLint-config (ESLint 9). Next 16 verwijdert `next lint`; we draaien de ESLint-CLI
// direct. `eslint-config-next/core-web-vitals` levert vanaf v16 een flat-config-array
// (voorheen `extends: "next/core-web-vitals"` in .eslintrc.json).
import nextCoreWebVitals from "eslint-config-next/core-web-vitals";

const config = [
  { ignores: [".next/**", "node_modules/**", "next-env.d.ts"] },
  ...nextCoreWebVitals,
  {
    rules: {
      // Nieuw in de Next 16-config (react-hooks-plugin). Vlagt het gangbare, door React
      // toegestane patroon "setState binnen een sync-/fetch-effect" (loading-flags,
      // index-resets) dat onder Next 15 groen was. Advies, geen correctheidsfout — op `warn`
      // gezet zodat de bump gedrag-neutraal blijft; een eventuele refactor is los werk.
      "react-hooks/set-state-in-effect": "warn",
    },
  },
  {
    // Config-modules exporteren bewust een anonieme default (framework-conventie).
    files: ["*.config.mjs", "*.config.js"],
    rules: { "import/no-anonymous-default-export": "off" },
  },
];

export default config;
