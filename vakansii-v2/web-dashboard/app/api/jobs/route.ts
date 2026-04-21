import { NextRequest, NextResponse } from "next/server";
import sql from "@/lib/db";

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const category = searchParams.get("category");
  const remote = searchParams.get("remote");
  const minSalary = searchParams.get("min_salary");
  const search = searchParams.get("search");

  let conditions = [sql`1=1`];
  if (category) conditions.push(sql`category = ${category}`);
  if (remote) conditions.push(sql`remote_type = ${remote}`);
  if (minSalary) conditions.push(sql`salary_min_usd >= ${parseInt(minSalary, 10)}`);
  if (search) conditions.push(sql`title ILIKE ${"%" + search + "%"}`);

  const jobs = await sql`
    SELECT * FROM jobs
    WHERE ${sql.join(conditions, sql` AND `)}
    ORDER BY published_at DESC
    LIMIT 200
  `;

  return NextResponse.json(jobs);
}
