"""
多源搜索引擎 — 百度百科 + Wikipedia + DuckDuckGo 并行搜索
"""
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS


def _baidu_baike(name: str, timeout: int = 10) -> str:
    """从百度百科获取人物简介（中文首选）"""
    try:
        url = f"https://baike.baidu.com/item/{requests.utils.quote(name)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": "https://baike.baidu.com/",
        }
        sess = requests.Session()
        # 先访问首页获取 cookie
        sess.get("https://baike.baidu.com/", headers=headers, timeout=timeout)
        resp = sess.get(url, headers=headers, timeout=timeout)
        if resp.status_code != 200:
            # 第一次失败，加个延后再试
            if resp.status_code == 403:
                return ""
            return ""

        soup = BeautifulSoup(resp.text, "html.parser")

        # 方法1：lemma-summary 段落
        summary_div = soup.find("div", class_="lemma-summary")
        if summary_div:
            text = summary_div.get_text(strip=True)
            if len(text) > 20:
                return text[:3000]

        # 方法2：basic-info 信息框
        basic_info = soup.find("div", class_="basic-info")
        if basic_info:
            text = basic_info.get_text(strip=True)
            if len(text) > 20:
                return text[:3000]

        # 方法3：正文段落（para 类）
        paras = soup.find_all("div", class_="para")
        if paras:
            parts = []
            for p in paras[:8]:
                text = p.get_text(strip=True)
                if len(text) > 15:
                    parts.append(text)
            if parts:
                return "\n".join(parts)[:3000]

        # 方法4：提取所有中文段落（兜底）
        texts = []
        for tag in soup.find_all(["p", "div"]):
            text = tag.get_text(strip=True)
            if len(text) > 30 and re.search(r'[一-鿿]{5,}', text):
                texts.append(text)
        if texts:
            return "\n".join(texts[:5])[:3000]

        return ""
    except Exception:
        return ""


def _wikipedia(name: str, lang: str = "zh", timeout: int = 10) -> str:
    """从 Wikipedia 获取条目简介"""
    try:
        api = f"https://{lang}.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "format": "json",
            "titles": name,
            "prop": "extracts",
            "exintro": True,
            "explaintext": True,
            "redirects": 1,
        }
        headers = {
            "User-Agent": "CharacterAgent/1.0 (chat-bot;请联系我们改进) python-requests",
            "Accept": "application/json",
        }
        resp = requests.get(api, params=params, headers=headers, timeout=timeout)
        if resp.status_code != 200:
            return ""
        data = resp.json()
        pages = data.get("query", {}).get("pages", {})
        for pid, page in pages.items():
            if pid != "-1":
                extract = page.get("extract", "")
                return extract[:3000]
        return ""
    except Exception:
        return ""


def _ddg_search(name: str, max_results: int = 3, timeout: int = 8) -> str:
    """DuckDuckGo 搜索（兜底）"""
    try:
        with DDGS(timeout=timeout) as ddgs:
            results = list(ddgs.text(name, max_results=max_results))
        parts = []
        for r in results:
            title = r.get("title", "")
            body = r.get("body", "")
            if title or body:
                parts.append(f"{title}：{body}" if title else body)
        return "\n".join(parts) if parts else ""
    except Exception:
        return ""


def search(name: str, timeout: int = 15) -> dict:
    """并行搜索所有来源，返回结构化结果"""
    tasks = {
        "baidu": lambda: _baidu_baike(name, timeout),
        "wikipedia": lambda: _wikipedia(name, timeout),
        "wikipedia_en": lambda: _wikipedia(name, "en", timeout),
        "web": lambda: _ddg_search(name, timeout),
    }

    results = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        future_map = {pool.submit(fn): key for key, fn in tasks.items()}
        for future in as_completed(future_map):
            key = future_map[future]
            try:
                text = future.result()
                if text:
                    results[key] = text
            except Exception:
                pass

    return results


def search_summary(name: str, timeout: int = 15) -> str:
    """搜索并合并为一段摘要文本（方便直接塞 prompt）"""
    results = search(name, timeout)
    parts = []

    if results.get("baidu"):
        parts.append(f"【百度百科】\n{results['baidu']}")
    if results.get("wikipedia"):
        parts.append(f"【维基百科】\n{results['wikipedia']}")
    if results.get("wikipedia_en"):
        parts.append(f"【Wikipedia】\n{results['wikipedia_en']}")
    if results.get("web"):
        parts.append(f"【网页搜索】\n{results['web']}")

    return "\n\n".join(parts)
