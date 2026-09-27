import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# 프로젝트 최상위의 .env 파일을 읽어옵니다.
load_dotenv()

DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME")

# PostgreSQL 연결 URL 구성 (TEST_DATABASE_URL이 있으면 우선 사용)
_test_url = os.getenv("TEST_DATABASE_URL")
if _test_url:
    SQLALCHEMY_DATABASE_URL = _test_url
    engine = create_engine(_test_url, connect_args={"check_same_thread": False})
else:
    SQLALCHEMY_DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    # 연결 풀 — 기본값은 SQLAlchemy 기본(5 + overflow 10, 대기 30초)과 동일해 동작 변화 없음.
    # RDS db.t4g.micro max_connections = 79. uvicorn 단일 프로세스 기준 최대 pool_size + max_overflow 개 사용.
    # 부하 측정(docs/performance.md) 결과에 따라 .env 로 조정한다.
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        pool_pre_ping=True,
        pool_size=int(os.getenv("DB_POOL_SIZE", "5")),
        max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "10")),
        pool_timeout=int(os.getenv("DB_POOL_TIMEOUT", "30")),
        pool_recycle=int(os.getenv("DB_POOL_RECYCLE", "1800")),  # 유휴 연결이 끊기기 전에 교체
    )
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# DB 세션 의존성 주입 함수 (나중에 API에서 사용)
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()