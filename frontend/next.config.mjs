/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      // Proxy API calls to the FastAPI backend during dev
      { source: "/api/:path*", destination: "http://localhost:8000/api/:path*" },
      { source: "/v1/:path*", destination: "http://localhost:8000/v1/:path*" },
    ];
  },
};
export default nextConfig;
