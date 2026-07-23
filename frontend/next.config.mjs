/** @type {import('next').NextConfig} */
const apiBaseUrl = process.env.API_INTERNAL_URL || "http://localhost:8000";

const nextConfig = {
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${apiBaseUrl}/api/:path*` },
      { source: "/v1/:path*", destination: `${apiBaseUrl}/v1/:path*` },
    ];
  },
};
export default nextConfig;
