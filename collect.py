import argparse
from sqlalchemy import create_engine, select, update, insert, MetaData, Table, desc
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
import os


def getRandom():
    metadata = MetaData()
    random_table = Table('random', metadata, autoload_with=engine)
    with engine.begin() as conn:
        select_stmt = (
            select(random_table.c.id)
            .where(random_table.c.is_used == 0)  # type: ignore
            .limit(1)
        )
        result = conn.execute(select_stmt)
        num = result.scalar()
        if num is None:
            raise ValueError("No available unused random IDs")
        update_stmt = (
            update(random_table)
            .where(random_table.c.id == num)  # type: ignore
            .values(is_used=1)
        )
        conn.execute(update_stmt)
        return num


def screenall():
    with SqlSession() as sql_session:
        undetermined_all_book = sql_session.query(Manga).filter(Manga.autostate == 1).all()  # type: ignore

        co = 0
        length = str(len(undetermined_all_book))

        for manga in undetermined_all_book:
            co += 1
            print(str(co) + '/' + length)
            flag = 0
            similarList = sql_session.query(Manga).filter(Manga.realname == manga.realname).all()  # type: ignore
            if flag == 1:
                manga.autostate = 2
                sql_session.commit()
            else:
                similarFlagList = []
                for similar in similarList:
                    score = similar.rating * 0.01 + similar.timestamp * 0.000000000001
                    if "無修正" in similar.name or "无修正" in similar.name:
                        if 'chinese' in similar.tag:
                            if similar.rating > 30:
                                similarFlagList.append(31 + score)
                            else:
                                similarFlagList.append(22 + score)
                        else:
                            similarFlagList.append(21 + score)
                    else:
                        if 'chinese' in similar.tag:
                            if similar.rating > 30:
                                similarFlagList.append(23 + score)
                            else:
                                similarFlagList.append(12 + score)
                        else:
                            similarFlagList.append(11 + score)

                res = ehentai_utils.screen(similarFlagList)
                random_num = getRandom()
                for i in range(len(res)):
                    if not (similarList[i].autostate != 1 or similarList[i].state is not None):
                        if res[i] == 1:
                            similarList[i].autostate = 2
                        else:
                            similarList[i].autostate = 3
                    similarList[i].relatetation = str(random_num)
                    sql_session.commit()


def updateTagTranslation():
    url = "https://github.com/EhTagTranslation/Database/releases/latest/download/db.text.json"
    target_file = "./db.text.json"
    temp_file = target_file + ".tmp"

    try:
        response = requests.get(url, stream=True, proxies=config.proxies1)
        response.raise_for_status()

        with open(temp_file, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        if os.path.exists(temp_file):
            if os.path.exists(target_file):
                os.replace(temp_file, target_file)
            else:
                os.rename(temp_file, target_file)
        print(f"文件已更新：{target_file}")

    except Exception as e:
        if os.path.exists(temp_file):
            os.remove(temp_file)
        print(f"下载失败: {e}")


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
            url = unext_a_soup.get("href")
            next_num = int(url.split("next=")[1].split("&")[0])
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

            languages = ['english', 'korean', 'russian', 'french', 'dutch', 'hungarian', 'italian', 'polish', 'portuguese', 'spanish', 'thai', 'vietnamese', 'ukrainian']
            if 'translated' in manga_metadata.tag and 'chinese' not in manga_metadata.tag:
                if any(lang in manga_metadata.tag for lang in languages):
                    continue

                nowtimestamp = int(time.time())
                manga_timestamp = int(datetime.datetime.strptime(manga_metadata.postedtime, "%Y-%m-%d %H:%M").timestamp())
                if nowtimestamp - manga_timestamp > 259200:
                    manga_metadata.autostate = '1'
                else:
                    manga_metadata.autostate = '-1'

            with SqlSession() as sql_session:
                sql_session.merge(manga_metadata)
                sql_session.commit()

        print("Insert success")

        now_page += 1
        time.sleep(5 + random.randint(0, 10))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--updatedb", action="store_true")
    args = parser.parse_args()

    engine = create_engine(config.sql_engine)
    SqlSession = sessionmaker(bind=engine)

    if args.updatedb == True:
        updateTagTranslation()
    else:
        conn = config.createDBconn()
        c = conn.cursor()

        with engine.begin() as conn:
            stmt = (
                select(Manga.manga_id)
                .where(Manga.autostate != -1)  # type: ignore
                .order_by(desc(Manga.postedtimestamp))
                .limit(1)
            )
            result = conn.execute(stmt)
            latest_id = result.scalar()

        pre = int(latest_id.split('/')[0])

        for collect_url in config.collect_url_list:
            collect(collect_url, 0, pre, config.collect_url_list[collect_url])

        screenall()

        try:
            updateTagTranslation()
        except:
            print('更新标签数据库失败')
        print('done')
