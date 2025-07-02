from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import sessionmaker
from model import Manga
import config
import ehentai_utils
import requests
from bs4 import BeautifulSoup
import datetime
import time
import re
import random


def collect(base_url, start, end, mark):
    se = requests.session()
    if start != 0:
        url = base_url + "&next=" + str(start)
    else:
        url = base_url

    dev = 0
    error_flag = 0
    now_page = 0
    next_num = 9999999999
    while next_num > end:
        proxy = config.proxy_pool[(datetime.datetime.now().hour + dev) % len(config.proxy_pool)]
        print(mark + ':' + str(now_page))
        print(url)
        old_url = url
        try:
            response = se.get(url, headers=config.header, cookies=config.cookies_non_donation, proxies=proxy)
            data_soup = BeautifulSoup(response.text, 'lxml')

            unext_a_soup = data_soup.find("a", id="unext")
            if unext_a_soup is None:
                unext_span_soup = data_soup.find("span", class_="unext")
                if unext_span_soup is None:
                    # print(response.text)
                    raise "request error"
                else:
                    next_num = 0
            else:
                url = unext_a_soup.get("href")
                next_num = int(url.split("next=")[1].split("&")[0])
                with open('full_collect_log.txt', 'a', encoding='utf-8') as file:
                    file.write(str(next_num) + '\n')
        except:
            print('request error')
            error_flag += 1
            url = old_url
            dev += 1
            if error_flag >= len(config.proxy_pool):
                raise 'request error'
            else:
                time.sleep(2)
                continue

        error_flag = 0

        total_info_soup = data_soup.find("table", class_="itg glte")
        list_tr_soup = total_info_soup.find_all("tr", recursive=False)
        print('find ', len(list_tr_soup))
        if len(list_tr_soup) != 25 and next_num != 0:
            raise 'find metadata error'

        for tr_soup in list_tr_soup:
            manga_metadata = ehentai_utils.parse_metadata(tr_soup)

            with SqlSession() as sql_session:
                existing_record = sql_session.get(Manga, manga_metadata.manga_id)
                if existing_record:
                    manga_metadata.state = None
                else:
                    manga_metadata.state = 1
                sql_session.merge(manga_metadata)
                sql_session.commit()

        print("Insert success")

        now_page += 1
        time.sleep(80 + random.randint(0, 40))


if __name__ == "__main__":
    engine = create_engine(config.sql_engine)
    SqlSession = sessionmaker(bind=engine)

    start = int(input("start"))

    collect("https://exhentai.org/?f_cats=704&f_search=lolicon", start, 0, "full")

    print('done')
