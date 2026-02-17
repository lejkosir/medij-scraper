from time import sleep
import cloudscraper
from bs4 import BeautifulSoup
import re
import json
from datetime import datetime
import threading
from tqdm import tqdm
import queue
import psycopg2 as pg

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
    try:
        timestamp = re.findall(timere, text)[0]
        hr, minut = timestamp.split(":") if ":" in timestamp else timestamp.split(".")
    except:
        hr, minut = 0, 0
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
    if clas:
        elements = soup.find_all(tag, class_=clas)
    else:
        elements = [el for el in soup.find_all(tag) if not el.has_attr('class')]
    # elements = soup.find_all(tag, class_=clas) if clas else soup.find_all(tag)
    text = '\n'.join(el.get_text(strip=True) for el in elements)
    cleaned = '\n'.join(line for line in text.splitlines() if line.strip())
    return cleaned


def failed(link, failfile="failed.txt"):
    with open("failed.txt", "a") as f:
        f.write(link + "\n")

def remove_unneeded(soup, tag, clas):
    for el in soup.find_all(tag, class_=clas):
        el.decompose()
    return soup

def process_link(link, config, cur, verbose=False, failfile="failed.txt"):
    site = link.split("/")[2]
    config = get_site_config(config, site)
    if not config:
        print("You are scraping a site that does not exist in the config file! If it is present, make sure url contains \"https://\"!")
    if verbose:
        print(config)
        print(link)
    scraper = cloudscraper.create_scraper()
    try:
        r = scraper.get(link.rstrip("\n"))
        r.encoding = "utf-8"
        scrapetext = r.text
        # print(scrapetext)
        soup = BeautifulSoup(scrapetext, 'lxml')
        if config["clean"]:
            for selector in config["clean"]:
                # if "action" in selector:
                match selector["action"]:
                    case "":
                        soup = remove_unneeded(soup, selector["tag"], selector["class"])
                    case "class":
                        for p in soup.find_all(selector["tag"], class_=selector["class"]):
                            del p["class"]
                # else:
                #     soup = remove_unneeded(soup, selector["tag"], selector["class"])
        if "title" in config and config["title"]:
            title = get_title(soup, config["title"]["tag"], config["title"]["class"])
        if "datetime" in config and config["datetime"]:
            dt = get_datetime(soup, config["datetime"]["tag"], config["datetime"]["class"])
        if "summary" in config and config["summary"]:
            summary = get_summary(soup, config["summary"]["tag"], config["summary"]["class"])
        if "body" in config and config["body"]:
            body = get_body(soup, config["body"]["tag"], config["body"]["class"])
            if "paywall" in config and config["paywall"]:
                p = get_body(soup, config["paywall"]["tag"], config["paywall"]["class"])
                if p:
                    body = "[[[PAYWALLED]]] " + body
        if verbose:
            print(title or "No title")
            print(dt or "No datetime")
            print(summary or "No summary")
            print(body or "No body")

        article_text = summary + " " + body
        words = len(article_text.split(" "))

        id = config["id"]

        cur.execute("""
            SELECT to_tsvector('simple', %s::text)
        """, (article_text,))
        tsv = cur.fetchone()[0]

        cur.execute("""SELECT 1 FROM articles WHERE url = (%s)""", (link,))

        if cur.fetchone()[0]:
            return "skip"
        
        if not words:
            failed(link, failfile)
            return "fail"

        cur.execute("""
                        INSERT INTO articles (url, title, datetime, words, medij_id, tsv)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """, (link, title, dt, words, id, tsv))
        con.commit()
        return "commit"




    except Exception as e:
        print(e)
        failed(link, failfile)
        return "fail"


def process_batch(links, pos, config, cursor, verbose=False, failfile="failed.txt", result_queue=None):
    fail = 0
    process = 0
    skipped = 0
    for link in tqdm(links, desc=f"Thread {pos}", position=pos, leave=False, dynamic_ncols=True):
        state = process_link(link, config, cursor, verbose, failfile)
        match state:
            case "commit":
                process += 1
            case "skip":
                skipped += 1
            case "fail":
                fail += 1
    result_queue.put((fail, process))
    return fail, process, skipped


if __name__ == "__main__":
    import argparse
    starttime = datetime.now()

    parser = argparse.ArgumentParser()
    parser.add_argument("-b", "--batch", help="file with links for batch processing")
    parser.add_argument("-c", "--config", help="json config file for sites", default="sites.json")
    parser.add_argument("-u", "--url", help="only one url to process")
    parser.add_argument("-t", "--threads", help="how many threads to use while bulk processing", type=int, default=1)
    parser.add_argument("-v", "--verbose", help="prints all processed text", action="store_true")
    parser.add_argument("-f", "--fail", help="file to save failed links to", default="failed.txt")
    parser.add_argument("-db", "--database", help="database connection string to save scraped data to", default="db.txt")
    args = parser.parse_args()

    if args.threads > 1 and not args.batch:
        parser.error("-t/--threads requires -b/--batch to be set")
    if not args.config:
        parser.error("-c/--config is required")
    if not args.batch and not args.url:
        parser.error("-f/--file or -u/--url is required")

    with open(args.database, "r") as f:
        conn_string = f.read()
    con = pg.connect(conn_string)

    with open(args.config, "r") as f:
        config = json.load(f)

    if args.batch:
        result_queue = queue.Queue()
        with open(args.batch, "r") as f:
            threads = []
            links = [line.strip() for line in f if line.strip()]
            num_threads = args.threads
            per_thread = (len(links) + num_threads - 1) // num_threads

            for i in range(num_threads):
                cur = con.cursor()
                chunk = links[i * per_thread : (i + 1) * per_thread]
                t = threading.Thread(target=process_batch, args=(chunk, i, config, cur, args.verbose, args.fail, result_queue))
                threads.append(t)
                # print(f"Starting thread {i}")
                t.start()
                sleep(1)

            for t in threads:
                t.join()

            tot_fail = 0
            tot_proc = 0
            tot_skipped = 0
            while not result_queue.empty():
                fail, proc, skip = result_queue.get()
                tot_fail += fail
                tot_proc += proc
                tot_skipped += skip
            endtime = datetime.now()
            time = endtime - starttime
            print()
            print(f"Finished in {time}")
            print(f"Failed: {tot_fail}, Processed: {tot_proc}, Skipped: {tot_skipped}")



    else:
        cur = con.cursor()
        res = process_link(args.url, config, cur, args.verbose, args.fail)
        endtime = datetime.now()
        time = endtime - starttime
        print(res)