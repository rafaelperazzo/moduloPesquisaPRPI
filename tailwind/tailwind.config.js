// Tailwind v3 compilado localmente (substitui o Play CDN cdn.tailwindcss.com).
// Gere o CSS com tailwind/build.sh sempre que um template ganhar classes novas.
/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    '../app/templates/**/*.html',
    '../app/static/js/**/*.js',
  ],
  theme: {
    extend: {},
  },
  plugins: [],
}
