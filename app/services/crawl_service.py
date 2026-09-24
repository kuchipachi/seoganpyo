import logging
import os
import re
import httpx
from bs4 import BeautifulSoup
from rapidfuzz import process, fuzz
from sqlalchemy.orm import Session
from app.models.professor import Professor, ProfessorDetail

logger = logging.getLogger(__name__)

BASE_URL = "https://cs.sogang.ac.kr"
LIST_URL = f"{BASE_URL}/cs/cs02_1_001.html"
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "exaone3.5:7.8b")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "300"))


DEFAULT_PROMPT = (
    "아래는 대학교수의 연구 소개입니다.\n"
    "이 교수님이 어떤 연구를 하는지 설명하고, 어떤 관심사를 가진 학생에게 추천하는지 2문장으로 작성해주세요.\n\n"
    "규칙:\n"
    "- 첫 문장: '이 교수님은 ~을 연구합니다.' 형식으로 연구 분야를 자연스럽게 소개\n"
    "- 둘째 문장: '~에 관심 있는 학생에게 추천합니다.' 형식으로 마무리\n"
    "- 연구 주제를 나열하지 말고 하나의 큰 흐름으로 표현\n"
    "- 전문용어는 영어 그대로 유지\n"
    "- 소개 문장만 출력 (부연 설명, 제목 없이)\n\n"
    "예시 출력: "
    "이 교수님은 딥러닝을 활용해 언어 모델이 더 잘 추론할 수 있도록 연구합니다. "
    "AI와 자연어 처리에 관심 있는 학생에게 추천합니다.\n\n"
)


def _summarize_research_area(text: str, prompt_override: str | None = None) -> str | None:
    text = text[:300]
    if not text or len(text) < 10:
        return None
    base_prompt = prompt_override if prompt_override else DEFAULT_PROMPT
    prompt = base_prompt + text
    try:
        with httpx.Client(timeout=OLLAMA_TIMEOUT) as client:
            res = client.post(OLLAMA_URL, json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "think": False,
                "options": {"think": False},
            })
            res.raise_for_status()
            text = res.json().get("response", "").strip()
            text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)
            text = re.sub(r"`+([^`]*)`+", r"\1", text)
            text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
            return text or None
    except Exception as e:
        logger.warning("[Ollama] 요약 실패: %s", e)
        return None


def _fetch(url: str) -> BeautifulSoup:
    with httpx.Client(timeout=10, follow_redirects=True) as client:
        res = client.get(url)
        res.raise_for_status()
    return BeautifulSoup(res.text, "html.parser")


def _normalize(text: str) -> str:
    return text.replace("\xa0", " ").strip()


def _extract_text_after_label(td, label: str) -> str | None:
    for tag in td.find_all(["b", "strong"]):
        if label in _normalize(tag.get_text()):
            node = tag.next_sibling
            while node:
                text = _normalize(node.get_text() if hasattr(node, "get_text") else str(node))
                text = text.lstrip(":").strip()
                if text:
                    return text
                node = node.next_sibling
    return None


def _clean_name(raw: str) -> str:
    name = re.sub(r"\(.*?\)", "", raw)
    name = re.sub(r"\s*(명예|겸직|초빙|특훈)?\s*교수", "", name)
    return name.strip()


def _parse_detail_page(url: str) -> dict:
    soup = _fetch(url)
    rows = soup.select("div.table_gsis table tr")
    result = {"name": None, "email": None, "specialty": None, "research_area": None, "homepage": None}

    if not rows:
        return result

    first_row_tds = rows[0].find_all("td")
    if len(first_row_tds) >= 2:
        info_td = first_row_tds[-1]
        left_td = first_row_tds[0]

        name_tag = left_td.find("strong") or left_td.find("span")
        if name_tag:
            result["name"] = _clean_name(name_tag.get_text(strip=True))

        result["specialty"] = (
            _extract_text_after_label(info_td, "세부전공")
            or _extract_text_after_label(info_td, "전공")
        )

        mailto = info_td.find("a", href=lambda h: h and h.startswith("mailto:"))
        if mailto:
            result["email"] = mailto.get_text(strip=True)
        else:
            result["email"] = (
                _extract_text_after_label(info_td, "e-mail")
                or _extract_text_after_label(info_td, "Email")
                or _extract_text_after_label(info_td, "E-mail")
            )

    for row in rows[1:]:
        row_text = row.get_text()
        if "연구분야" not in row_text and "홈페이지" not in row_text:
            continue
        detail_td = row.find("td")
        if not detail_td:
            continue

        for a_tag in detail_td.find_all("a", href=True):
            href = a_tag.get("href", "")
            if href.startswith("http"):
                result["homepage"] = href
                break

        td_html = str(detail_td)
        if "연구분야" in td_html:
            after = td_html.split("연구분야", maxsplit=1)[1]
            after = re.sub(r"^[^<>]*>", "", after)
            after = after.lstrip(": \n").strip()
            after = re.sub(r"</td>.*$", "", after, flags=re.DOTALL).strip()
            after = re.sub(r"<(script|style)[^>]*>.*?</(script|style)>", "", after, flags=re.DOTALL | re.IGNORECASE)
            if after:
                result["research_area"] = after
        break

    return result


def _parse_list_page() -> list[dict]:
    soup = _fetch(LIST_URL)
    professors = []
    for row in soup.select("div.table_gsis table tr"):
        tds = row.find_all("td")
        if len(tds) < 2:
            continue
        info_td = tds[-1]
        name_span = info_td.find("span", style=lambda s: s and "16pt" in s)
        if not name_span:
            continue
        name = _clean_name(name_span.get_text(strip=True))
        if not name:
            continue
        link = info_td.find("a", class_="tx-link")
        href = link["href"] if link and link.get("href") else None
        detail_url = (href if href.startswith("http") else BASE_URL + href) if href else None
        professors.append({"name": name, "detail_url": detail_url})
    return professors


def _to_plain(html: str) -> str:
    if "<" in html:
        return BeautifulSoup(html, "html.parser").get_text(separator=" ").strip()
    return html


def crawl_and_upsert(db: Session) -> dict:
    web_professors = _parse_list_page()
    db_professors = db.query(Professor).all()
    db_name_map = {p.name: p for p in db_professors}
    db_names = list(db_name_map.keys())

    updated = []
    not_found_in_db = []

    for wp in web_professors:
        web_name = wp["name"]

        matched_professor = db_name_map.get(web_name)
        match_type = "exact" if matched_professor else None
        matched_db_name = web_name if matched_professor else None

        if not matched_professor and db_names:
            fuzzy_result = process.extractOne(web_name, db_names, scorer=fuzz.ratio)
            if fuzzy_result and fuzzy_result[1] >= 85:
                matched_professor = db_name_map[fuzzy_result[0]]
                match_type = "fuzzy"
                matched_db_name = fuzzy_result[0]

        if not matched_professor:
            not_found_in_db.append({"web_name": web_name, "detail_url": wp["detail_url"]})
            continue

        crawl_error = None
        detail = {}
        if wp["detail_url"]:
            try:
                detail = _parse_detail_page(wp["detail_url"])
            except Exception as e:
                crawl_error = str(e)

        existing = db.query(ProfessorDetail).filter(
            ProfessorDetail.professor_id == matched_professor.professor_id
        ).first()

        research_area = detail.get("research_area")
        research_area_plain = _to_plain(research_area) if research_area else None
        existing_plain = _to_plain(existing.research_area) if existing and existing.research_area else None

        if research_area_plain != existing_plain and research_area_plain:
            print(f"[Ollama] {web_name} 요약 중...", flush=True)
            research_summary = _summarize_research_area(research_area_plain)
            if research_summary:
                print(f"[Ollama] {web_name} 완료", flush=True)
        else:
            research_summary = existing.research_summary if existing else None

        fields = {
            "name": detail.get("name") or web_name,
            "email": detail.get("email"),
            "specialty": detail.get("specialty"),
            "research_area": research_area,
            "research_summary": research_summary,
            "homepage": detail.get("homepage"),
        }

        if existing:
            for k, v in fields.items():
                setattr(existing, k, v)
        else:
            db.add(ProfessorDetail(professor_id=matched_professor.professor_id, **fields))

        updated.append({
            "web_name": web_name,
            "db_name": matched_db_name,
            "match_type": match_type,
            "detail_url": wp["detail_url"],
            "crawl_error": crawl_error,
            "saved": {k: v for k, v in fields.items() if k != "research_area"},
        })

    db.commit()

    web_names_set = {wp["name"] for wp in web_professors}
    db_only = [
        p.name for p in db_professors
        if p.name not in web_names_set
        and not process.extractOne(p.name, list(web_names_set), scorer=fuzz.ratio, score_cutoff=85)
    ]

    return {
        "updated_count": len(updated),
        "not_found_count": len(not_found_in_db),
        "db_only_count": len(db_only),
        "updated": updated,
        "not_found_in_db": not_found_in_db,
        "db_only": db_only,
    }
