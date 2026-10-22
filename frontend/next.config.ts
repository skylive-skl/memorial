import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

const backendUrl = process.env.BACKEND_INTERNAL_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  // URL Django заканчиваются на «/»; не даём Next срезать слэш редиректом.
  skipTrailingSlashRedirect: true,
  // Браузер ходит только на Next: API и Swagger проксируются на Django (один origin для cookie).
  async rewrites() {
    return [
      // `:path*` теряет завершающий «/», поэтому вариант со слэшем — отдельным правилом.
      { source: "/api/v1/:path*/", destination: `${backendUrl}/api/v1/:path*/` },
      { source: "/api/v1/:path*", destination: `${backendUrl}/api/v1/:path*` },
      { source: "/api/schema/", destination: `${backendUrl}/api/schema/` },
      { source: "/api/docs/", destination: `${backendUrl}/api/docs/` },
    ];
  },
};

const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

export default withNextIntl(nextConfig);
