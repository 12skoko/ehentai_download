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
    errorflag = 0
    url = baseurl
    nowPage = 0
    nextnum = 9999999999
    while (nextnum > end):
        proxy = config.proxyPool[(datetime.datetime.now().hour + dev) % len(config.proxyPool)]
        print(mark + ':' + str(nowPage))
        print(url)
        old_url = url
        try:
            response = se.get(url, headers=config.header, cookies=config.cookies, proxies=proxy)
            data = response.text
            re_next = """<a id=\"dnext\" href=\"(.*?next=(\d+))\">Next"""
            url_res = re.search(re_next, data)
            url = url_res[1].replace("amp;", "")
            nextnum = int(url_res[2])
        except:
            print('error')
            errorflag += 1
            url = old_url
            dev += 1
            if errorflag >= len(config.proxyPool):
                raise 'error'
            else:
                time.sleep(2)
                continue

        errorflag = 0
        re_info = """<div class=\"cn ct.\" onclick=\".*?\">(.*?)</div>.*?<div onclick=\"popUp.*?\" id=\"postedpop_.+?\">(.*?)</div>.*?<div class=\"ir\" style=\"background-position:-?(\d+)px -?(\d+)px;opacity:1\"></div>.*?<div class=\"gldown\">(.*?)</div>.*?<a href=\"(https://exhentai.org/g/(.*?)/)\"><div class=\"glink\">(.*?)</div><div>(.*?)</div></a>.*?<div>(\d+) pages</div>"""
        resList = re.findall(re_info, data)
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
                if fatch[0][16] != -1:
                    continue
                else:
                    exist = 1
            if nowtimestamp - timestamp > 259200:
                autostate = '1'
            else:
                autostate = '-1'

            if exist == 0:
                sqlstr = f'INSERT INTO manga (id,name,link,torrentlink,time,type,tag,pages,rating,autostate,realname,timestamp)values("{id}","{name}","{link}","{torrentLink}","{timestr}","{type}","{tag}",{pages},{rating},{autostate},"{realname}","{timestamp}");'
            else:
                sqlstr = f'UPDATE manga SET id="{id}",name="{name}",link="{link}",torrentlink="{torrentLink}",time="{timestr}",type="{type}",tag="{tag}",pages={pages},rating={rating},autostate={autostate},realname="{realname}",timestamp="{timestamp}" WHERE id="{id}";'

            print(sqlstr)
            c.execute(sqlstr)
            conn.commit()


        nowPage += 1
        time.sleep(5 + random.randint(0, 10))




def screenall():
    sqlstr = 'SELECT * FROM manga WHERE autostate = 1;'
    c.execute(sqlstr)
    undetermined_all_book = c.fetchall()

    count = {}
    co = 0
    length = str(len(undetermined_all_book))

    for manga in undetermined_all_book:
        co += 1
        print(str(co) + '/' + length)

        similarList = []
        realname = manga[13]
        flag = 0
        sqlstr = 'SELECT * FROM manga;'
        c.execute(sqlstr)
        all_book = c.fetchall()
        for manga2 in all_book:
            if realname == manga2[13]:
                flag += 1
                similarList.append(manga2)
        if flag in count:
            count[flag] += 1
        else:
            count[flag] = 1
        if flag == 1:
            sqlstr = 'UPDATE manga SET autostate = 2 WHERE id="' + manga[0] + '";'
            print(manga[1], sqlstr)
            c.execute(sqlstr)
            conn.commit()
        else:
            similarFlagList = []
            for similar in similarList:
                score = similar[8] * 0.01 + similar[10] * 0.000000000001
                if "無修正" in similar[1] or "无修正" in similar[1]:
                    if 'chinese' in similar[6]:
                        if similar[8] > 30:
                            similarFlagList.append(31 + score)
                        else:
                            similarFlagList.append(22 + score)
                    else:
                        similarFlagList.append(21 + score)
                else:
                    if 'chinese' in similar[6]:
                        if similar[8] > 30:
                            similarFlagList.append(23 + score)
                        else:
                            similarFlagList.append(12 + score)
                    else:
                        similarFlagList.append(11 + score)
            res = screen(similarFlagList)
            random_num = getRandom()
            for i in range(len(res)):
                sqlstr = f'SELECT * FROM manga WHERE (autostate!=1 OR state is NOT NULL) and id="{similarList[i][0]}";'
                c.execute(sqlstr)
                restemp = c.fetchall()
                if restemp:
                    sqlstr = 'UPDATE manga SET relatetation = %s WHERE id= "%s";' % (str(random_num), similarList[i][0])
                else:
                    if res[i] == 1:
                        sqlstr = 'UPDATE manga SET autostate = 2 , relatetation = %s WHERE id= "%s";' % (
                            str(random_num), similarList[i][0])
                    else:
                        sqlstr = 'UPDATE manga SET autostate = 3 , relatetation = %s WHERE id= "%s";' % (
                            str(random_num), similarList[i][0])
                print(sqlstr)
                c.execute(sqlstr)
                conn.commit()


conn = config.conn
c = conn.cursor()

sqlstr = 'SELECT id FROM manga WHERE autostate!=-1 ORDER BY timestamp DESC LIMIT 1;'
c.execute(sqlstr)
pre = int(c.fetchall()[0][0].split('/')[0])

se = requests.session()
for collect_url in config.collect_url_list:
    collect(collect_url, pre, config.collect_url_list[collect_url])

screenall()
print('done')
