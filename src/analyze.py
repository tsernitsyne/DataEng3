from collections import Counter, defaultdict
from itertools import combinations
from statistics import median


def percentile(values, share):
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * share
    left = int(index)
    right = min(left + 1, len(ordered) - 1)
    return ordered[left] + (ordered[right] - ordered[left]) * (index - left)


def analyze(vacancies, count_rows):
    frequencies = {
        tuple(row["skills"]): row["frequency"]
        for row in count_rows
    }
    salaries = defaultdict(list)
    region_frequencies = Counter()
    region_salaries = defaultdict(list)
    by_region = defaultdict(list)

    for vacancy in vacancies:
        area = vacancy["area"]
        by_region[area].append(vacancy)
        for size in (1, 2, 3):
            for skills in combinations(vacancy["skills"], size):
                region_frequencies[(area, skills)] += 1
                if vacancy["salary"] is not None:
                    salaries[skills].append(vacancy["salary"])
                    region_salaries[(area, skills)].append(vacancy["salary"])

    top_frequency = {}
    for size in (1, 2, 3):
        ranked = sorted(
            (row for row in count_rows if row["size"] == size),
            key=lambda row: (-row["frequency"], row["skills"]),
        )
        top_frequency[str(size)] = ranked[:10]

    effects = []
    for skills, frequency in frequencies.items():
        size = len(skills)
        if size not in (2, 3) or len(salaries[skills]) < 20:
            continue

        possible_bases = combinations(skills, size - 1)
        base = min(possible_bases, key=lambda item: (-frequencies[item], item))
        if len(salaries[base]) < 20:
            continue

        full_median = median(salaries[skills])
        base_median = median(salaries[base])
        effects.append({
            "size": size,
            "skills": list(skills),
            "frequency": frequency,
            "salary_count": len(salaries[skills]),
            "median": full_median,
            "base": list(base),
            "base_frequency": frequencies[base],
            "base_salary_count": len(salaries[base]),
            "base_median": base_median,
            "difference": full_median - base_median,
        })

    top_effects = {}
    for size in (2, 3):
        candidates = [row for row in effects if row["size"] == size]
        top_effects[f"{size}_up"] = sorted(
            (row for row in candidates if row["difference"] > 0),
            key=lambda row: (-row["difference"], -row["salary_count"], row["skills"]),
        )[:5]
        top_effects[f"{size}_down"] = sorted(
            (row for row in candidates if row["difference"] < 0),
            key=lambda row: (row["difference"], -row["salary_count"], row["skills"]),
        )[:5]

    areas = sorted(by_region, key=lambda area: (-len(by_region[area]), area))[:3]
    regions = []
    region_top_stacks = {}

    for area in areas:
        rows = by_region[area]
        pay = [row["salary"] for row in rows if row["salary"] is not None]
        regions.append({
            "area": area,
            "vacancies": len(rows),
            "with_skills": sum(bool(row["skills"]) for row in rows),
            "salary_count": len(pay),
            "median": median(pay) if pay else None,
            "q25": percentile(pay, 0.25),
            "q75": percentile(pay, 0.75),
        })

        region_top_stacks[area] = {}
        for size in (1, 2, 3):
            ranked = sorted(
                (
                    (skills, frequency)
                    for (region, skills), frequency in region_frequencies.items()
                    if region == area and len(skills) == size
                ),
                key=lambda item: (-item[1], item[0]),
            )[:3]
            region_top_stacks[area][str(size)] = [
                {
                    "skills": list(skills),
                    "frequency": frequency,
                    "salary_count": len(region_salaries[(area, skills)]),
                    "median": (
                        median(region_salaries[(area, skills)])
                        if region_salaries[(area, skills)]
                        else None
                    ),
                }
                for skills, frequency in ranked
            ]

    all_pay = [row["salary"] for row in vacancies if row["salary"] is not None]
    return {
        "vacancies": len(vacancies),
        "with_skills": sum(bool(row["skills"]) for row in vacancies),
        "salary_count": len(all_pay),
        "median_salary": median(all_pay),
        "top_frequency": top_frequency,
        "top_effects": top_effects,
        "effects_considered": len(effects),
        "regions": regions,
        "region_top_stacks": region_top_stacks,
    }
