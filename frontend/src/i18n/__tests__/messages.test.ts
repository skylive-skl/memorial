import { describe, expect, it } from "vitest";

import en from "../../../messages/en.json";
import ru from "../../../messages/ru.json";
import uz from "../../../messages/uz.json";
import { routing } from "../routing";

function flattenKeys(obj: object, prefix = ""): string[] {
  return Object.entries(obj).flatMap(([key, value]) => {
    const path = prefix ? `${prefix}.${key}` : key;
    return value !== null && typeof value === "object" ? flattenKeys(value, path) : [path];
  });
}

const messages = { ru, uz, en };

describe("messages", () => {
  it("есть файл переводов для каждой локали", () => {
    expect(Object.keys(messages).sort()).toEqual([...routing.locales].sort());
  });

  it.each(["uz", "en"] as const)("ключи %s совпадают с ru", (locale) => {
    expect(flattenKeys(messages[locale]).sort()).toEqual(flattenKeys(ru).sort());
  });
});
