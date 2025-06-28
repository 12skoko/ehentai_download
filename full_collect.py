import requests
import re
import time
import random
import config
import datetime
import html


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


def calRating(a, b):
    rating = (5 - int(a) // 16) * 10
    if b == '21':
        rating -= 5
    return rating


def tagParse(tagstr):
    re_tag = """>([a-z:]+?)<"""
    tag = re.findall(re_tag, tagstr)
    return ','.join(tag)


def collect(baseurl, start, end, mark):
    if start != '0':
        url = baseurl + "&next=" + str(start)
    else:
        url = baseurl
    dev = 0
    nowPage = 0
    nextnum = 9999999999
    while (nextnum > end):
        proxy = config.proxyPool[(datetime.datetime.now().hour + dev) % len(config.proxyPool)]
        print(mark + ':' + str(nowPage))
        print(url)
        response = se.get(url, headers=config.header, cookies=config.cookies, proxies=proxy)
        data = response.text
        try:
            re_next = """<a id=\"dnext\" href=\"(.*?next=(\d+))\">Next"""
            url_res = re.search(re_next, data)
            url = url_res[1].replace("amp;", "")
            nextnum = int(url_res[2])
            with open('full_collect.txt', 'a', encoding='utf-8') as file:
                file.write(str(nextnum) + '\n')
        except:
            nextnum = 0

        re_info = """<div class=\"cn ct.\" onclick=\".*?\">(.*?)</div>.*?<div onclick=\"popUp.*?\" id=\"postedpop_.+?\">(.*?)</div>.*?<div class=\"ir\" style=\"background-position:-?(\d+)px -?(\d+)px;opacity:1\"></div>.*?<div class=\"gldown\">(.*?)</div>.*?<a href=\"(https://exhentai.org/g/(.*?)/)\"><div class=\"glink\">(.*?)</div><div>(.*?)</div></a>.*?<div>(\d+) pages</div>"""
        resList = re.findall(re_info, data)
        print('find ', len(resList))
        if len(resList) != 25 and nextnum != 0:
            # print(data)
            raise 're error'
        for res in resList:
            id = res[6]
            name = html.unescape(res[7]).replace('"', '""')
            link = res[5]
            try:
                re_torrentLink = """<a href=\"(https://exhentai\.org/gallerytorrents\.php\?gid=.*?&amp;t=.*?)\""""
                torrentLink = re.search(re_torrentLink, res[4])[1].replace("amp;", "")
            except:
                torrentLink = ''
            timestr = res[1]
            type = res[0]
            tag = tagParse(res[8])
            pages = res[9]
            rating = calRating(res[2], res[3])
            realname = getRealname(name)
            timestamp = int(datetime.datetime.strptime(timestr, "%Y-%m-%d %H:%M").timestamp())
            nowtimestamp = int(time.time())
            exist = 0

            sqlstr = f'SELECT id FROM manga where id="{id}";'
            c.execute(sqlstr)
            fatch = c.fetchall()
            if fatch:
                exist = 1

            state = 16

            if exist == 0:
                sqlstr = f'INSERT INTO manga (id,name,link,torrentlink,time,type,tag,pages,rating,state,realname,timestamp)values("{id}","{name}","{link}","{torrentLink}","{timestr}","{type}","{tag}",{pages},{rating},{state},"{realname}","{timestamp}");'
            else:
                sqlstr = f'UPDATE manga SET torrentlink="{torrentLink}",time="{timestr}",tag="{tag}",pages={pages},rating={rating},timestamp="{timestamp}" WHERE id="{id}";'

            # print(sqlstr)
            try:
                c.execute(sqlstr)
                conn.commit()
            except Exception as e:
                print(e)
                print(sqlstr)
                raise 'sql error'

        print("insert success")
        nowPage += 1
        time.sleep(60 + random.randint(0, 20))


se = requests.session()

conn = config.createDBconn()
c = conn.cursor()

baseurl = 'https://exhentai.org/?f_cats=704&f_search=lolicon'

start = input("start")

collect(baseurl, start, 0, baseurl.split('/')[-1])

print('done')
