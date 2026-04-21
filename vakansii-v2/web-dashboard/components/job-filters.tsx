"use client";

import { useQueryState } from "nuqs";

const CATEGORIES = [
  "Backend",
  "Frontend",
  "Fullstack",
  "DevOps",
  "Data Science",
  "QA",
  "Design",
  "PM",
  "Prompt Engineering",
  "Other",
];

const REMOTE_TYPES = ["FULLY_REMOTE", "HYBRID", "ONSITE"];

export function JobFilters() {
  const [category, setCategory] = useQueryState("category");
  const [remote, setRemote] = useQueryState("remote");
  const [minSalary, setMinSalary] = useQueryState("min_salary");
  const [search, setSearch] = useQueryState("search");

  const handleReset = () => {
    setCategory(null);
    setRemote(null);
    setMinSalary(null);
    setSearch(null);
  };

  return (
    <div className="mb-6 flex flex-wrap items-center gap-4">
      <select
        value={category || ""}
        onChange={(e) => setCategory(e.target.value || null)}
        className="h-10 rounded-md border border-neutral-800 bg-neutral-900 px-3 text-sm text-neutral-100"
      >
        <option value="">Все категории</option>
        {CATEGORIES.map((c) => (
          <option key={c} value={c}>
            {c}
          </option>
        ))}
      </select>

      <select
        value={remote || ""}
        onChange={(e) => setRemote(e.target.value || null)}
        className="h-10 rounded-md border border-neutral-800 bg-neutral-900 px-3 text-sm text-neutral-100"
      >
        <option value="">Все форматы</option>
        {REMOTE_TYPES.map((r) => (
          <option key={r} value={r}>
            {r === "FULLY_REMOTE" ? "Удаленно" : r === "HYBRID" ? "Гибрид" : "Офис"}
          </option>
        ))}
      </select>

      <input
        type="number"
        placeholder="Мин. зарплата USD"
        value={minSalary || ""}
        onChange={(e) => setMinSalary(e.target.value || null)}
        className="h-10 w-48 rounded-md border border-neutral-800 bg-neutral-900 px-3 text-sm text-neutral-100 placeholder:text-neutral-500 focus:outline-none focus:ring-2 focus:ring-neutral-700"
      />

      <input
        type="text"
        placeholder="Поиск..."
        value={search || ""}
        onChange={(e) => setSearch(e.target.value || null)}
        className="h-10 w-64 rounded-md border border-neutral-800 bg-neutral-900 px-3 text-sm text-neutral-100 placeholder:text-neutral-500 focus:outline-none focus:ring-2 focus:ring-neutral-700"
      />

      <button
        onClick={handleReset}
        className="h-10 rounded-md border border-neutral-700 bg-neutral-900 px-4 text-sm text-neutral-300 hover:bg-neutral-800 hover:text-neutral-100"
      >
        Сбросить
      </button>
    </div>
  );
}
