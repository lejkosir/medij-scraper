import cloudscraper
from bs4 import BeautifulSoup
import re
import requests
import json
from datetime import datetime

def get_site_config(config, target_url):
    for site in config["sites"]:
        if site["url"] == target_url:
            return site
    return None

def get_title(soup, tag, clas):
    title = soup.find(tag, class_=clas) if clas else soup.find(tag)
    return title.get_text()

def get_datetime(soup, tag, clas):
    datere = re.compile(r"[123]?\d[.].*?\d{4}")
    timere = re.compile(r"(?:[0-1]?\d|2[0-3])[:.][0-5]\d")
    datetimestring = soup.find(tag, class_=clas) if clas else soup.find(tag)
    text = datetimestring.get_text()
    date = re.findall(datere, text)[0]
    timestamp = re.findall(timere, text)[0]
    hr, minut = timestamp.split(":") if ":" in timestamp else timestamp.split(".")
    dt = veliki_datetime_decryptor(date, minut, hr)
    return dt


def veliki_datetime_decryptor(datest, minute, hour):
    date_re = re.compile(
        r"(?P<day>\d{1,2})[.\s]*"
        r"(?P<month>\d{1,2}|[A-Za-z]{3,9})[.\s]*"
        r"(?P<year>\d{4})",
        re.IGNORECASE
    )
    match = date_re.search(datest)
    if match:
        day = match.group("day")
        month = match.group("month")
        year = match.group("year")
    month_map = {
        "januar": 1, "februar": 2, "marec": 3, "april": 4,
        "maj": 5, "junij": 6, "julij": 7, "avgust": 8,
        "september": 9, "oktober": 10, "november": 11, "december": 12,
        "jan": 1, "feb": 2, "mar": 3, "apr": 4,
        "jun": 6, "jul": 7, "avg": 8, "sep": 9,
        "okt": 10, "nov": 11, "dec": 12
    }
    month = month.lower() if type(month) == str else month
    month = month_map[month] if month in month_map else month
    dt = datetime(int(year), int(month), int(day), int(hour), int(minute))
    return dt

def get_summary(soup, tag, clas):
    summary = soup.find(tag, class_=clas) if clas else soup.find(tag)
    return summary.get_text()

def get_body(soup, tag, clas):
    elements = soup.find_all(tag, class_=clas) if clas else soup.find_all(tag)
    text = '\n'.join(el.get_text(strip=True) for el in elements)
    cleaned = '\n'.join(line for line in text.splitlines() if line.strip())
    return cleaned


def failed(link):
    ## dodaj v file
    pass

def remove_unneeded(soup, tag, clas):
    for el in soup.find_all(tag, class_=clas):
        el.decompose()
    return soup

def process_link(link, config):
    site = link.split("/")[2]
    config = get_site_config(config, site)
    if not config:
        print("Scrapeaš stran, ki ni v sites.json. Poglej ali tvoj url vsebuje \"https://\"")
    print(config)
    scraper = cloudscraper.create_scraper()
    try:
        r = scraper.get(link.rstrip("\n"))
        r.encoding = "utf-8"
        scrapetext = r.text
        # print(scrapetext)
        soup = BeautifulSoup(scrapetext, 'lxml')
        if config["clean"]:
            for selector in config["clean"]:
                soup = remove_unneeded(soup, selector["tag"], selector["class"])
        if "title" in config:
            if config["title"]:
                title = get_title(soup, config["title"]["tag"], config["title"]["class"])
                print(title)
        if "datetime" in config:
            if config["datetime"]:
                dt = get_datetime(soup, config["datetime"]["tag"], config["datetime"]["class"])
                print(dt)
        if "summary" in config:
            if config["summary"]:
                summary = get_summary(soup, config["summary"]["tag"], config["summary"]["class"])
                print(summary)
        if "body" in config:
            if config["body"]:
                body = get_body(soup, config["body"]["tag"], config["body"]["class"])
                print(body)


    except:
        failed(link)

## test
link = ""
with open("sites.json", "r") as f:
    config = json.load(f)
process_link(link, config)