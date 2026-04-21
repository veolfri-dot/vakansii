import { JobFilters } from "@/components/job-filters";
import { JobGrid } from "@/components/job-grid";
import { CommandMenu } from "@/components/command-menu";
import { StoreHydrator } from "@/components/store-hydrator";

export const dynamic = "force-dynamic";

type SearchParams = Promise<{ [key: string]: string | string[] | undefined }>;

export default async function Home(props: { searchParams: SearchParams }) {
  const searchParams = await props.searchParams;

  const params = new URLSearchParams();
  const category =
    typeof searchParams.category === "string" ? searchParams.category : undefined;
  const remote =
    typeof searchParams.remote === "string" ? searchParams.remote : undefined;
  const minSalary =
    typeof searchParams.min_salary === "string"
      ? parseInt(searchParams.min_salary, 10)
      : undefined;
  const search =
    typeof searchParams.search === "string" ? searchParams.search : undefined;

  if (category) params.set("category", category);
  if (remote) params.set("remote", remote);
  if (minSalary && !isNaN(minSalary)) params.set("min_salary", String(minSalary));
  if (search) params.set("search", search);

  const res = await fetch(
    `${process.env.NEXT_PUBLIC_APP_URL || "http://localhost:3000"}/api/jobs?${params.toString()}`,
    { cache: "no-store" }
  );

  if (!res.ok) {
    throw new Error("Ошибка загрузки вакансий");
  }

  const jobs = await res.json();

  return (
    <main className="min-h-screen p-6">
      <div className="mx-auto max-w-7xl">
        <div className="mb-8 flex items-center justify-between">
          <h1 className="text-3xl font-bold tracking-tight">
            Агрегатор удаленных IT-вакансий
          </h1>
        </div>
        <JobFilters />
        <JobGrid initialJobs={jobs || []} />
        <StoreHydrator jobs={jobs || []} />
        <CommandMenu />
      </div>
    </main>
  );
}
