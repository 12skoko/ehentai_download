import re
from datetime import datetime
from bs4 import BeautifulSoup as bs
import os
import config
import config_picacg


def getRealname(name):
    length = len(name)
    s = 0
    m = 0
    l = 0
    r = length
    for i in range(length):
        ch = name[i]
        if (s == 0 and m == 0) and (ch != '(' and ch != '[' and ch != ' '):
            l = i
            break
        elif ch == '(':
            s += 1
        elif ch == '[':
            m += 1
        elif ch == ')':
            s -= 1
        elif ch == ']':
            m -= 1
    for i in range(length - 1, -1, -1):
        ch = name[i]
        if (s == 0 and m == 0) and (ch != ')' and ch != ']' and ch != ' '):
            r = i + 1
            break
        elif ch == ')':
            s += 1
        elif ch == ']':
            m += 1
        elif ch == '(':
            s -= 1
        elif ch == '[':
            m -= 1
    realname = name[l:r]
    return realname

conn = config.createDBconn()
c = conn.cursor()

nowtime = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

filepath = config_picacg.picacg_main_filepath
entries = os.listdir(filepath)

for fname in entries:

    cids = []
    with open(os.path.join(filepath, fname, "cid.txt"), 'r', encoding='utf-8') as f:
        for line in f:
            res = re.search(r'\d+: "([\da-f]+)"', line)
            if res:
                cids.append(res[1])
    # print(len(cids))
    # print(cids)
    # exit()

    main_page_path = os.path.join(filepath, fname, "index.html")

    with open(main_page_path, "r", encoding="utf-8") as file:
        html_content = file.read()

    soup = bs(html_content, "lxml")
    items = soup.find_all('li', class_='cat-item')
    # print(len(items))

    if len(cids) != len(items):
        raise "len(cids)!=len(items)"

    i = 0
    for item in items:
        results = item.select('div.comic-title')
        if len(results) != 1:
            raise "len(comic-title) != 1"
        name = results[0].text.replace("(完)", "").strip()

        results = item.select('div.comic-author')
        if len(results) != 1:
            raise "len(comic-title) != 1"
        author = results[0].find("span", class_="c-author").text.strip()

        results = item.select('div.c-list-cat')
        if len(results) != 1:
            raise "len(comic-title) != 1"
        classification = results[0].find("span", class_="c-cat").text.strip()

        favorited = item.find("span", class_="c-score text-muted pe-1").text.strip()

        cid = cids[i]

        realname = getRealname(name)

        link = config_picacg.picacg_base_url+cid

        category = 'Manga'

        i += 1

        sqlstr = 'INSERT IGNORE INTO manga_picacg (cid, name, link, realname, category, classification, author, favorited, state, crawltime )values("%s", "%s", "%s", "%s", "%s", "%s", "%s", %s, %s, "%s");' % (
        cid, name, link, realname, category, classification, author, favorited, '1', nowtime)

        try:
            c.execute(sqlstr)
        except Exception as e:
            print(sqlstr)
            print(e)
            raise "sql error"
        conn.commit()

    # break
