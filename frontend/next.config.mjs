/** @type {import('next').NextConfig} */
const apiBaseUrl = process.env.API_INTERNAL_URL || "http://localhost:8000";

const nextConfig = {
  // Next's built-in gzip compression buffers the whole response before
  // writing anything out — fine for normal pages, but it defeats every
  // proxied /api/* SSE stream (chat, workflow runs): the browser sees
  // nothing until the backend closes the connection, however long that
  // takes. That's invisible for plain streaming text (it just arrives less
  // "live"), but it breaks the Client Tool Bridge outright: a ui_* tool
  // blocks server-side waiting for the browser to answer a ui_action event
  // it never actually received in time, and times out. Real compression
  // still happens at Cloudflare/Caddy in front of this process.
  compress: false,
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
