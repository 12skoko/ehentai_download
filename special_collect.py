import requests
import re
import time
import random
import config
import datetime
import html
import winsound


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


def getRandom():
    sqlstr = 'SELECT id FROM random WHERE is_used=0 LIMIT 1;'
    c.execute(sqlstr)
    num = c.fetchall()[0][0]
    sqlstr = 'UPDATE random SET is_used=1 WHERE id=' + str(num) + ';'
    c.execute(sqlstr)
    conn.commit()
    return num


def select(lists):
    sorted_list = sorted(lists, key=lambda x: x[0], reverse=True)
    return sorted_list[0][1]


def screen(similarFlagList):
    res = [0] * len(similarFlagList)
    filterDict1 = {1: [], 2: [], 3: []}
    for i in range(len(similarFlagList)):
        similarFlag = similarFlagList[i]
        filterDict1[similarFlag // 10].append((round(similarFlag - (similarFlag // 10) * 10, 12), i))
    if filterDict1[3] != []:
        filterDict2 = filterDict1[3]
    elif filterDict1[2] != []:
        filterDict2 = filterDict1[2]
    else:
        filterDict2 = filterDict1[1]
    filterDict3 = {}
    for i in filterDict2:
        if int(i[0]) in filterDict3:
            filterDict3[int(i[0])].append((round(i[0] - int(i[0]), 12), i[1]))
        else:
            filterDict3[int(i[0])] = [(round(i[0] - int(i[0]), 12), i[1])]
    for i in filterDict3:
        res[select(filterDict3[i])] = 1
    return res


def calRating(a, b):
    rating = (5 - int(a) // 16) * 10
    if b == '21':
        rating -= 5
    return rating


def tagParse(tagstr):
    re_tag = """>([a-z:]+?)<"""
    tag = re.findall(re_tag, tagstr)
    return ','.join(tag)


def collect(baseurl, end, mark):
    dev = 0
    url = baseurl
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
        except:
            nextnum = 0

        re_info = """<div class=\"cn ct.\" onclick=\".*?\">(.*?)</div>.*?<div onclick=\"popUp.*?\" id=\"postedpop_.+?\">(.*?)</div>.*?<div class=\"ir\" style=\"background-position:-?(\d+)px -?(\d+)px;opacity:1\"></div>.*?<div class=\"gldown\">(.*?)</div>.*?<a href=\"(https://exhentai.org/g/(.*?)/)\"><div class=\"glink\">(.*?)</div><div>(.*?)</div></a>.*?<div>(\d+) pages</div>"""
        resList = re.findall(re_info, data)
        print('find ',len(resList))
        if len(resList)==0:
            raise 'error'
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

            sqlstr = f'SELECT * FROM manga where id="{id}";'
            c.execute(sqlstr)
            fatch = c.fetchall()
            if fatch:
                if fatch[0][9] == 0 or fatch[0][9] == 13:
                    continue
                elif fatch[0][9] == 2 or fatch[0][9] == 6 or fatch[0][9] == 3 or fatch[0][16] == 3:
                    exist = 1
                else:
                    print('-------------------------------', fatch[0][0], fatch[0][1])
                    winsound.Beep(1000, 5000)
                    continue

            state = 13

            if exist == 0:
                sqlstr = f'INSERT INTO manga (id,name,link,torrentlink,time,type,tag,pages,rating,state,realname,timestamp)values("{id}","{name}","{link}","{torrentLink}","{timestr}","{type}","{tag}",{pages},{rating},{state},"{realname}","{timestamp}");'
            else:
                sqlstr = f'UPDATE manga SET id="{id}",name="{name}",link="{link}",torrentlink="{torrentLink}",time="{timestr}",type="{type}",tag="{tag}",pages={pages},rating={rating},state={state},realname="{realname}",timestamp="{timestamp}" WHERE id="{id}";'

            print(sqlstr)
            c.execute(sqlstr)
            conn.commit()

        nowPage += 1
        time.sleep(20 + random.randint(0, 20))


se = requests.session()

conn = config.conn
c = conn.cursor()

artist=[
    # 'tamano kedama',
    # 'rico',
    # 'mutou mato',
    # 'kunisaki kei',
    # 'yukiu con',
    # 'usashiro mani',
    # 'ronna',
    # 'petenshi',
    # 'fujisaka lyric',
    # 'nogiwa kaede',
    # 'yuizaki kazuya',
    # 'ginyou haru',
    # 'kiira',
    # 'azuma yuki',
    # 'okada kou'
    # 'muk',
    'fummy',
    'shouji ayumu'

]

for art in artist:
    url='https://exhentai.org/tag/artist:'+art.replace(' ','+')+'?f_sft=on&f_sfu=on'
    print(url)
    collect(url, 0, art)

print('done')
