"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import type { CountryInfo } from "../lib/types";

export default function CountrySwitcher({
  countries,
  selected,
}: {
  countries: CountryInfo[];
  selected: string;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  // Nothing to switch between yet (e.g. before a second country has real
  // inflation_metrics rows) — see api.ts's getCountries().
  if (countries.length <= 1) return null;

  function handleChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const params = new URLSearchParams(searchParams.toString());
    params.set("country", e.target.value);
    router.push(`${pathname}?${params.toString()}`);
  }

  return (
    <select
      value={selected}
      onChange={handleChange}
      aria-label="Country"
      className="rounded border border-neutral-700 bg-neutral-900 px-3 py-1.5 text-sm text-neutral-200 hover:bg-neutral-800"
    >
      {countries.map((c) => (
        <option key={c.code} value={c.code}>
          {c.name}
        </option>
      ))}
    </select>
  );
}
