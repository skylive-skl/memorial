import createMiddleware from "next-intl/middleware";

import { routing } from "./i18n/routing";

export default createMiddleware(routing);

export const config = {
  // Всё, кроме:
  // - /api (прокси на Django и route handlers Next),
  // - /m и /m/... (публичная страница без префикса языка — короткий URL для QR),
  // - служебных путей Next и файлов с точкой (favicon.ico и т. п.).
  matcher: "/((?!api|m(?:/|$)|_next|_vercel|.*\\..*).*)",
};
