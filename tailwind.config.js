// Readdy 시안의 색 체계: 각 색은 bapsang.css의 oklch 변수(--색-단계)를 가리킨다.
const scale = (name) =>
  Object.fromEntries([50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950]
    .map((k) => [k, `oklch(var(--${name}-${k}) / <alpha-value>)`]));

module.exports = {
  content: ["./web/index.html", "./web/p.html", "./web/app.js"],
  theme: {
    extend: {
      colors: {
        background: scale("background"), primary: scale("primary"), accent: scale("accent"),
        secondary: scale("secondary"), foreground: scale("foreground"),
      },
      fontFamily: {
        heading: ["var(--font-heading)"], body: ["var(--font-body)"], sans: ["var(--font-body)"],
        label: ["var(--font-label)"], hand: ["var(--font-hand)"],
      },
    },
  },
};
