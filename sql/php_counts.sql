CREATE TEMP TABLE php_rows AS
SELECT
    source || ':' || vacancy_id AS id,
    list_sort(
        list_distinct(
            list_filter(
                list_transform(
                    string_split(coalesce(key_skills, ''), ';'),
                    skill -> lower(trim(skill, ' ' || chr(9) || chr(10) || chr(13)))
                ),
                skill -> skill <> ''
            )
        )
    ) AS skills
FROM read_csv(
    '__S3_URI__',
    header = true,
    all_varchar = true,
    max_line_size = 20000000,
    parallel = false
)
WHERE lower(trim(role)) = 'программист, разработчик'
  AND regexp_matches(
      lower(name),
      '(^|[^\p{L}\p{N}_])php($|[^\p{L}\p{N}_])'
  );

WITH single_skills AS (
    SELECT
        id,
        unnest(skills) AS skill,
        generate_subscripts(skills, 1) AS position
    FROM php_rows
),
skill_sets AS (
    SELECT [a.skill] AS skills
    FROM single_skills a

    UNION ALL

    SELECT [a.skill, b.skill]
    FROM single_skills a
    JOIN single_skills b
      ON a.id = b.id AND a.position < b.position

    UNION ALL

    SELECT [a.skill, b.skill, c.skill]
    FROM single_skills a
    JOIN single_skills b
      ON a.id = b.id AND a.position < b.position
    JOIN single_skills c
      ON a.id = c.id AND b.position < c.position
)
SELECT
    len(skills) AS size,
    skills,
    count(*) AS frequency
FROM skill_sets
GROUP BY skills
ORDER BY size, skills;
