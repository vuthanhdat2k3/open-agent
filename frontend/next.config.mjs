/** @type {import('next').NextConfig} */
const apiBaseUrl = process.env.API_INTERNAL_URL || "http://localhost:8000";

const nextConfig = {
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${apiBaseUrl}/api/:path*` },
      { source: "/v1/:path*", destination: `${apiBaseUrl}/v1/:path*` },
    ];
  },
  async headers() {
    return [
      {
        // Every page here is an authenticated client-side shell, so the HTML
        // itself carries no user data and is cheap to re-fetch. Next would
        // otherwise serve the prerendered document with `s-maxage=31536000`,
        // which keeps already-open tabs (and any proxy) pinned to the
        // previous deployment's markup and chunk names. Hashed assets under
        // /_next/static keep their own immutable caching.
        source: "/:path((?!_next/static).*)",
        headers: [{ key: "Cache-Control", value: "no-store, must-revalidate" }],
      },
    ];
  },
};
export default nextConfig;
