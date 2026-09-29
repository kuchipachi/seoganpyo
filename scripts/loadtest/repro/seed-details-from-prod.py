"""재현 DB 에 운영과 같은 강의·교수 details 를 채운다 — 응답 크기를 운영(약 130KB)과 맞추기 위함.

재현 DB 는 강의 37개만 시드돼 details 가 비어 있어 강의 목록 응답이 15KB 였다.
직렬화 비용이 운영보다 훨씬 작아 처리량을 부풀려 잰다 (docs/performance.md §4.3).

사용법 (운영 공개 API 를 1회 조회 — 로그인 불필요, 페이지 한 번 여는 것과 같음):
  curl -s "https://<운영 도메인>/backend/api/v1/courses?year=2026&semester=1" > prod.json
  curl -s "http://localhost:18000/api/v1/courses?year=2026&semester=1" > local.json
  python3 seed-details-from-prod.py prod.json local.json | docker exec -i repro-db-1 psql -U postgres -d seoganpyo -q

강의는 (과목코드, 요일, 시작 시각, 교수 이름), 교수는 재현 DB 의 professor_id 로 매칭한다.
"""
import json
import sys


def q(v):
    return "NULL" if v is None else "'" + str(v).replace("'", "''") + "'"


def key(c):
    return (c["course_code"], c["class_days"], c["class_start_time"], (c["professor"] or {}).get("name"))


def main(prod_path, local_path):
    prod = json.load(open(prod_path))
    local = json.load(open(local_path))
    by_key = {key(c): c for c in prod}
    assert len(by_key) == len(prod), "운영 응답에서 매칭 키가 중복됨"

    out, seen_prof, miss = [], set(), 0
    for c in local:
        p = by_key.get(key(c))
        if not p:
            miss += 1
            continue
        d = p["details"]
        if d:
            out.append(
                "INSERT INTO course_details (course_id,required_skills,evaluation_method,teaching_method,"
                "track_id,keyword,overview,pdf_hash,recommendation) VALUES (%d,%s,%s,%s,%s,%s,%s,%s,%s);" % (
                    c["course_id"], q(d["required_skills"]), q(d["evaluation_method"]), q(d["teaching_method"]),
                    q(d["track_id"]), q(d["keyword"]), q(d["overview"]), q(d["pdf_hash"]), q(d["recommendation"])))
        pd = (p["professor"] or {}).get("details")
        pid = c["professor_id"]
        if pd and pid and pid not in seen_prof:
            seen_prof.add(pid)
            out.append(
                "INSERT INTO professor_details (professor_id,name,email,specialty,research_area,research_summary,"
                "homepage) VALUES (%d,%s,%s,%s,%s,%s,%s);" % (
                    pid, q(c["professor"]["name"]), q(pd["email"]), q(pd["specialty"]),
                    q(pd["research_area"]), q(pd["research_summary"]), q(pd["homepage"])))

    print(f"-- 강의 {len(local) - miss}/{len(local)} 매칭, 교수 {len(seen_prof)}명", file=sys.stderr)
    print("BEGIN;\n" + "\n".join(out) + "\nCOMMIT;")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
