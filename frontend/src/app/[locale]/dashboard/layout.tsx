import { useTranslations } from "next-intl";

import { Link } from "@/i18n/navigation";

import styles from "./dashboard.module.css";

export default function DashboardLayout({ children }: LayoutProps<"/[locale]/dashboard">) {
  const t = useTranslations("Dashboard");

  return (
    <div className={styles.shell}>
      <header className={styles.header}>
        <Link href="/" className={styles.brand}>
          {t("brand")}
        </Link>
        <nav className={styles.nav}>
          <Link href="/dashboard">{t("nav.memorials")}</Link>
        </nav>
      </header>
      <main className={styles.main}>{children}</main>
    </div>
  );
}
