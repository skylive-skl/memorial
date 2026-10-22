import { useTranslations } from "next-intl";

import { Link } from "@/i18n/navigation";

export default function LandingPage() {
  const t = useTranslations("Landing");

  return (
    <main className="landing">
      <h1>{t("title")}</h1>
      <p>{t("subtitle")}</p>
      <Link href="/dashboard">{t("toDashboard")}</Link>
    </main>
  );
}
