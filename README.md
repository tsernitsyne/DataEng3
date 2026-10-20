# Домашняя работа №3: вариант 5 (PHP)

В работе используются вакансии из CSV за 2024 год. Исходный файл загружается в RustFS, после чего MapReduce и DuckDB независимо читают его через S3 и считают частоты навыков, пар и троек.

## Файлы

- `src/start_rustfs.py` запускает четыре локальных узла RustFS.
- `src/mapreduce.py` читает объект S3 чанками по 1000 вакансий.
- `sql/php_counts.sql` содержит запрос DuckDB.
- `src/duckdb_counts.py` выполняет SQL-запрос.
- `src/analyze.py` считает зарплаты и показатели трёх регионов.
- `src/run_all.py` загружает данные, делает три измерения каждого метода, сравнивает полные результаты и сохраняет итоговые CSV в S3.
- `report/main.tex` — исходник отчёта LaTeX.

## Запуск

Нужны Python 3.12, RustFS 1.0.0 и файл `it_vacancies_2024.csv`.

```powershell
python -m pip install -r requirements.txt
$env:AWS_ACCESS_KEY_ID = '<локальный ключ>'
$env:AWS_SECRET_ACCESS_KEY = '<локальный секрет>'
$env:S3_ENDPOINT = 'http://127.0.0.1:9110'
$env:DUCKDB_EXTENSION_DIRECTORY = "$PWD\.duckdb-extensions"
python -c "import duckdb,os; c=duckdb.connect(config={'extension_directory':os.environ['DUCKDB_EXTENSION_DIRECTORY']}); c.execute('INSTALL httpfs')"
python src/start_rustfs.py --binary '<путь к rustfs.exe>'
```

Сервер нужно оставить работающим. В другом терминале с теми же переменными окружения:

```powershell
python src/run_all.py --csv '<путь к it_vacancies_2024.csv>'
```

Программы берут роль «Программист, разработчик» и отдельное слово PHP в названии. Навыки разделяются по `;`, приводятся к нижнему регистру и учитываются один раз на вакансию. Зарплата сравнивается только для вакансий с `RUR/RUB` и `gross=false`; если указаны обе границы, используется их среднее.

Объекты лежат в бакете `hh-lake`: `raw/it_vacancies_2024.csv`, `segments/php.csv` и `results/php/skills_1.csv`, `skills_2.csv`, `skills_3.csv`. Локальные ключи и исходный CSV в репозиторий не включаются.
