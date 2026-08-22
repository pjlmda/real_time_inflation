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
    <div className="relative shrink-0">
      <select
        value={selected}
        onChange={handleChange}
        aria-label="Country"
        className="appearance-none rounded-md border border-hairline bg-surface py-1.5 pl-3 pr-8 text-sm text-ink2 transition-colors hover:text-ink"
      >
        {countries.map((c) => (
          <option key={c.code} value={c.code} className="bg-surface text-ink">
            {c.name}
          </option>
        ))}
      </select>
      {/* Native <select> chevron is replaced so it doesn't clash with the
          rest of the (custom-styled) UI — appearance-none above hides it. */}
      <svg
        aria-hidden
        viewBox="0 0 20 20"
        className="pointer-events-none absolute right-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink3"
      >
        <path d="M5.5 7.5L10 12l4.5-4.5" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </div>
  );
}
