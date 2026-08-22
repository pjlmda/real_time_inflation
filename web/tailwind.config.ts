import type { Config } from "tailwindcss";

// Dark-mode slots from the project's validated data-viz palette (not ad hoc
// Tailwind defaults — every value here passed the palette's CVD/contrast
// validator against this exact dark surface). Named by role so components
// reach for `bg-surface`/`text-ink2`/`text-chart1` etc. instead of raw
// `neutral-800`/`blue-400`, which is how every card ended up an identical
// bordered rectangle with no real hierarchy.
const config: Config = {
  content: ["./app/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        plane: "#0d0d0d", // page background
        surface: "#1a1a19", // card background — one step lighter than plane, reads as elevated
        surface2: "#232322", // nested/secondary surface (e.g. chart track, inner cards)
        ink: "#ffffff", // primary text
        ink2: "#c3c2b7", // secondary text
        ink3: "#898781", // muted text — axis labels, captions
        hairline: "rgba(255,255,255,0.10)", // card borders, dividers
        gridline: "#2c2c2a", // chart gridlines
        baseline: "#383835", // chart axis line
        // Categorical, fixed order — slot 1 always the same series identity.
        chart1: "#3987e5", // blue
        chart2: "#d95926", // orange
        // Status — reserved, never reused for series identity.
        good: "#0ca30c",
        warn: "#fab219",
        serious: "#ec835a",
        bad: "#d03b3b",
      },
    },
  },
  plugins: [],
};

export default config;
