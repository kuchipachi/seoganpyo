# scripts/migrations

학교 서버 DB(운영 데이터가 있던 시절)를 모델 변경에 맞춰 **보정하던 1회성 SQL** 입니다.

## 신규 DB(AWS RDS)에는 적용하지 않습니다 — 2026-09-26 검증

테이블은 `Base.metadata.create_all()` 로 모델에서 바로 생성되고, 아래 변경은 모두 모델에 이미 반영돼 있습니다.
RDS 실제 스키마와 대조한 결과:

| 파일 | 내용 | RDS 상태 | 적용 |
| --- | --- | --- | --- |
| `001_add_professor_department.sql` | `professors.department` 추가·NOT NULL | 컬럼 존재, NOT NULL, varchar(50) (인덱스는 없음 — 행 수가 적어 불필요) | ❌ |
| `002_resync_professors_sequence.sql` | 시퀀스를 MAX(id) 로 재동기화 | 시퀀스 = MAX(id) | ❌ |
| `003_normalize_course_category.sql` | `course_category` 를 전공/교양으로 정규화 | 규칙 위반 0건 (시드가 규칙대로 적재) | ❌ |
| `004_widen_professor_name.sql` | `professors.name` varchar(255) | 이미 255 | ❌ |
| `005_move_multi_prof_to_liberal.sql` | 다중 교수("A, B") → 교양 | 해당 0건 | ❌ |
| `006_recompute_is_retake.sql` | `histories.is_retake` 재계산 | 수강이력 0건 | ❌ |

## 앞으로 스키마를 바꿀 때

`create_all()` 은 **없는 테이블만 만들고 기존 테이블의 컬럼 변경은 반영하지 않습니다.**
운영 RDS 에 데이터가 쌓인 뒤 컬럼을 추가·변경하면 여기에 `007_...sql` 을 추가하고,
SSH 터널로 RDS 에 직접 적용하세요 (PR 템플릿의 "DB 컬럼 추가 시 ALTER TABLE 스크립트 포함").
