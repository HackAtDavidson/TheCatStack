"""Read public job descriptions; never treat a blocked page as a job description."""
from __future__ import annotations

import html
import ipaddress
import json
import re
import socket
import ssl
import threading
import time
from html.parser import HTMLParser
from urllib.error import HTTPError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener
from urllib.robotparser import RobotFileParser

import certifi

from .core import clean, web_url

USER_AGENT = "HackDavidsonOpportunities/1.0"
MAX_BYTES = 3_000_000


def public_url(url: str) -> str:
    parts = urlsplit(web_url(url))
    if parts.port not in (None, 80, 443):
        raise ValueError("Only public HTTP(S) job pages are supported")
    addresses = socket.getaddrinfo(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80))
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError("Job links must resolve to public internet addresses")
    return url


class PublicRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class PageText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.json_ld = [], []
        self.hidden = 0
        self.script_type = ""
        self.script = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self.hidden += 1
            if tag == "script":
                self.script_type = dict(attrs).get("type", "")
                self.script = []
        elif tag in {"p", "li", "div", "br", "h1", "h2", "h3"} and not self.hidden:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"}:
            if tag == "script" and self.script_type == "application/ld+json":
                try:
                    self.json_ld.append(json.loads("".join(self.script)))
                except ValueError:
                    pass
            self.hidden = max(0, self.hidden - 1)
            self.script_type = ""
        elif tag in {"p", "li", "div", "h1", "h2", "h3"} and not self.hidden:
            self.parts.append("\n")

    def handle_data(self, data):
        if self.hidden:
            if self.script_type == "application/ld+json":
                self.script.append(data)
        else:
            self.parts.append(data)

    def text(self):
        return "\n".join(re.sub(r"\s+", " ", line).strip() for line in "".join(self.parts).splitlines() if line.strip())


def plain_text(value: str) -> str:
    parser = PageText()
    parser.feed(html.unescape(value or ""))
    return parser.text()


def job_objects(value):
    if isinstance(value, list):
        for item in value:
            yield from job_objects(item)
    elif isinstance(value, dict):
        types = value.get("@type", [])
        if types == "JobPosting" or isinstance(types, list) and "JobPosting" in types:
            yield value
        yield from job_objects(value.get("@graph", []))


def same_title(expected: str, actual: str) -> bool:
    words = set(re.findall(r"[a-z0-9]+", expected.casefold())) - {"intern", "internship", "the", "and", "summer", "2027", "2026"}
    actual_words = set(re.findall(r"[a-z0-9]+", actual.casefold()))
    return bool(words) and len(words & actual_words) / len(words) >= 0.6


def parse_page(body: str, expected_title: str) -> dict:
    parser = PageText()
    parser.feed(body)
    jobs = [job for value in parser.json_ld for job in job_objects(value)]
    for job in jobs:
        if same_title(expected_title, job.get("title", "")):
            return {"title": job.get("title", ""), "text": plain_text(job.get("description", "")),
                    "posted": job.get("datePosted", ""), "deadline": job.get("validThrough", ""),
                    "format": "JobPosting metadata"}
    if jobs:
        raise ValueError("Page contains a different job; identity could not be verified")
    text = parser.text()
    if re.search(r"verify you are human|access denied|enable javascript|checking your browser|captcha", text, re.I):
        raise ValueError("Page requires browser interaction or blocks automated access")
    if len(text) < 350 or not same_title(expected_title, text[:2000]):
        raise ValueError("Could not identify a complete description for this job")
    return {"title": expected_title, "text": text[:80_000], "posted": "", "deadline": "", "format": "Public HTML"}


def supported_ats(url: str) -> bool:
    return urlsplit(url).hostname in {"job-boards.greenhouse.io", "boards.greenhouse.io", "jobs.lever.co", "jobs.eu.lever.co", "jobs.ashbyhq.com"}


class JobReader:
    def __init__(self, timeout: int = 12):
        self.timeout = timeout
        self.locks, self.robots, self.memo = {}, {}, {}
        self.guard = threading.Lock()

    def _request(self, url):
        public_url(url)
        context = ssl.create_default_context()
        context.load_verify_locations(cafile=certifi.where())
        opener = build_opener(PublicRedirects(), HTTPSHandler(context=context))
        request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json,text/html,text/plain"})
        with opener.open(request, timeout=self.timeout) as response:
            data = response.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                raise ValueError("Job page exceeds the 3 MB limit")
            return data.decode(response.headers.get_content_charset() or "utf-8", errors="replace")

    def read(self, url: str, api: bool = False) -> str:
        parts = urlsplit(url)
        host = parts.netloc
        with self.guard:
            lock = self.locks.setdefault(host, threading.Lock())
        with lock:
            if url in self.memo:
                return self.memo[url]
            if not api:
                if host not in self.robots:
                    robots_url = f"{parts.scheme}://{host}/robots.txt"
                    parser = RobotFileParser(robots_url)
                    try:
                        parser.parse(self._request(robots_url).splitlines())
                    except HTTPError as error:
                        if error.code == 404:
                            parser.parse([])
                        else:
                            raise ValueError(f"Could not verify robots.txt: HTTP {error.code}") from error
                    self.robots[host] = parser
                if not self.robots[host].can_fetch(USER_AGENT, url):
                    raise ValueError("Site robots.txt disallows this page")
            time.sleep(0.25)
            result = self._request(url)
            self.memo[url] = result
            return result

    def job(self, row: dict) -> dict:
        url = row["url"]
        parts = urlsplit(url)
        path = [quote(segment, safe="") for segment in parts.path.strip("/").split("/")]
        host = parts.hostname
        result = None
        if host in {"job-boards.greenhouse.io", "boards.greenhouse.io"} and len(path) >= 3 and path[1] == "jobs":
            item = json.loads(self.read(f"https://boards-api.greenhouse.io/v1/boards/{path[0]}/jobs/{path[2]}", api=True))
            result = {"title": item["title"], "text": plain_text(item.get("content", "")),
                      "posted": item.get("first_published", ""), "deadline": item.get("application_deadline", ""), "format": "Greenhouse API"}
        elif host in {"jobs.lever.co", "jobs.eu.lever.co"} and len(path) >= 2:
            api_host = "api.eu.lever.co" if host == "jobs.eu.lever.co" else "api.lever.co"
            item = json.loads(self.read(f"https://{api_host}/v0/postings/{path[0]}/{path[1]}", api=True))
            sections = [item.get("descriptionPlain", ""), item.get("additionalPlain", ""), item.get("salaryDescriptionPlain", "")]
            sections += [section.get("text", "") + "\n" + plain_text(section.get("content", "")) for section in item.get("lists", [])]
            result = {"title": item["text"], "text": "\n".join(sections), "posted": "", "deadline": "", "format": "Lever API"}
        elif host == "jobs.ashbyhq.com" and len(path) >= 2:
            data = json.loads(self.read(f"https://api.ashbyhq.com/posting-api/job-board/{path[0]}?includeCompensation=true", api=True))
            item = next((job for job in data["jobs"] if urlsplit(job.get("jobUrl", "")).path.rstrip("/").split("/")[-1] == path[1]), None)
            if not item or not item.get("isListed", True):
                raise ValueError("Job is no longer publicly listed")
            result = {"title": item["title"], "text": item.get("descriptionPlain") or plain_text(item.get("descriptionHtml", "")),
                      "posted": item.get("publishedAt", ""), "deadline": "", "format": "Ashby API"}
        if result is None:
            result = parse_page(self.read(url), row["title"])
        if not same_title(row["title"], result["title"]) or len(result["text"]) < 150:
            raise ValueError("Incomplete description or job title differs from the source listing")
        return {**result, "url": url, "text": clean(result["text"])[:80_000]}
