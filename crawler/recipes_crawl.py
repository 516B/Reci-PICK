import requests
from bs4 import BeautifulSoup
import json
import time
import re
import sqlite3
import os

BASE_URL = "https://www.10000recipe.com"
headers = {
    "User-Agent": "Mozilla/5.0"
}

# 카테고리(cat4 번호 기반)
categories = {
    "밑반찬": 63,
    "메인반찬": 56,
    "국/탕": 54,
    "찌개": 55,
    "양식": 65,
    "디저트": 60,
    "퓨전": 61,
    "빵": 66
}

# 재료 정제
def clean_ingredient(text):
    text = text.replace("구매", "").strip()
    parts = re.split(r'\n{2,}|\s{2,}', text)
    if len(parts) >= 2:
        name = parts[0].strip()
        amount = parts[1].strip()
        return name, amount
    return None, None

# 인분 추출
def extract_serving(category_text):
    match = re.search(r'(\d+\s*인분)', category_text)
    return match.group(1) if match else category_text.strip()

# 레시피 ID 추출 (cat4 기준)
def get_recipe_ids_by_cat4(cat4, max_count=60):
    ids = set()
    page = 1
    while len(ids) < max_count:
        url = f"{BASE_URL}/recipe/list.html?cat4={cat4}&page={page}"
        try:
            res = requests.get(url, headers=headers, timeout=5)
            res.raise_for_status()
        except Exception as e:
            print("카테고리 페이지 요청 실패:", e)
            break

        soup = BeautifulSoup(res.text, "lxml")
        links = soup.select(".common_sp_link")
        if not links:
            break
        for link in links:
            rid = link["href"].split("/")[-1]
            ids.add(rid)
            if len(ids) >= max_count:
                break
        page += 1
        time.sleep(0.3)
    return list(ids)

# 상세 레시피 정보 추출
def get_recipe_detail(recipe_id, category_name):
    url = f"{BASE_URL}/recipe/{recipe_id}"
    try:
        res = requests.get(url, headers=headers, timeout=5)
        res.raise_for_status()
    except Exception as e:
        print("레시피 요청 실패:", e)
        return None

    soup = BeautifulSoup(res.text, "lxml")

    title_tag = soup.select_one(".view2_summary h3")
    title = title_tag.text.strip() if title_tag else "제목 없음"

    category_tag = soup.select_one(".view2_summary_info1")
    category_raw = category_tag.text.strip() if category_tag else ""
    serving = extract_serving(category_raw)

    image_tag = soup.select_one(".centeredcrop img")
    image_url = image_tag["src"] if image_tag and image_tag.has_attr("src") else ""

    cook_time_tag = soup.select_one(".view2_summary_info2")
    cook_time = cook_time_tag.text.strip() if cook_time_tag else ""

    difficulty_tag = soup.select_one(".view2_summary_info3")
    difficulty = difficulty_tag.text.strip() if difficulty_tag else ""

    raw_ingredients = soup.select(".ready_ingre3 ul li")
    ingredient_dict = {}
    for item in raw_ingredients:
        if item.text.strip():
            name, amount = clean_ingredient(item.text)
            if name and amount:
                ingredient_dict[name] = amount

    steps = [step.text.strip() for step in soup.select(".view_step_cont") if step.text.strip()]

    return {
        "id": recipe_id,
        "title": title,
        "category": category_name,
        "serving": serving,
        "image_url": image_url,
        "cook_time": cook_time,
        "difficulty": difficulty,
        "ingredients": ingredient_dict,
        "steps": steps
    }

# 전체 수집 및 저장
all_recipes = []

for category_name, cat4 in categories.items():
    print("카테고리:", category_name, "(cat4 =", cat4, ")")
    recipe_ids = get_recipe_ids_by_cat4(cat4, max_count=60)
    print("수집 대상 ID 수:", len(recipe_ids))

    for rid in recipe_ids:
        try:
            print("크롤링 중:", rid)
            recipe = get_recipe_detail(rid, category_name)
            if recipe:
                all_recipes.append(recipe)
            time.sleep(0.5)
        except Exception as e:
            print("레시피 수집 실패:", e)

# 현재 파일 기준 저장 경로 설정
base_dir = os.path.dirname(os.path.abspath(__file__))
json_path = os.path.join(base_dir, "recipes.json")
db_path = os.path.join(base_dir, "recipes.db")

# JSON 저장
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(all_recipes, f, ensure_ascii=False, indent=2)

print("총", len(all_recipes), "개의 레시피가", json_path, "에 저장되었습니다.")

# SQLite 저장
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS recipes (
    id TEXT PRIMARY KEY,
    title TEXT,
    category TEXT,
    serving TEXT,
    image_url TEXT,
    cook_time TEXT,
    difficulty TEXT,
    ingredients TEXT,
    steps TEXT
)
""")

for recipe in all_recipes:
    cursor.execute(
        """
        INSERT OR REPLACE INTO recipes (
            id, title, category, serving, image_url, cook_time, difficulty, ingredients, steps
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            recipe["id"],
            recipe["title"],
            recipe["category"],
            recipe["serving"],
            recipe["image_url"],
            recipe["cook_time"],
            recipe["difficulty"],
            json.dumps(recipe["ingredients"], ensure_ascii=False),
            json.dumps(recipe["steps"], ensure_ascii=False)
        )
    )

conn.commit()
conn.close()

print("모든 작업 완료. JSON 및 SQLite 파일이 현재 코드 파일과 같은 위치에 저장되었습니다.")
