import type { NextConfig } from "next";

// Dans Docker Compose, "localhost" désigne le conteneur web lui-même.
// On cible donc le service "api" via API_INTERNAL_URL (défini dans docker-compose.yml).
const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${API_INTERNAL_URL}/:path*` },
    ];
  },
};

export default nextConfig;
