import { hasLocale } from "next-intl";
import { getRequestConfig } from "next-intl/server";
import * as rootParams from "next/root-params";
import { notFound } from "next/navigation";

import { routing } from "./routing";

export default getRequestConfig(async ({ locale }) => {
  // Явно переданная локаль — для маршрутов вне [locale] (например, /m/[code],
  // где язык берётся из memorial.language).
  if (!locale) {
    const paramValue = await rootParams.locale();
    if (!hasLocale(routing.locales, paramValue)) {
      notFound();
    }
    locale = paramValue;
  }

  return {
    locale,
    messages: (await import(`../../messages/${locale}.json`)).default,
  };
});
