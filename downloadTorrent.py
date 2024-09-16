import time
import requests
import re
import random
import config
import datetime
import qbittorrentapi

qbt_client = qbittorrentapi.Client(**config.qbit_login)
qbt_client.auth_log_in()

conn = config.conn
c = conn.cursor()

se = requests.session()

sqlstr = 'SELECT * FROM manga WHERE autostate=2 ORDER BY timestamp DESC;'

c.execute(sqlstr)
mangaList = c.fetchall()
lense = len(mangaList)
dev = 0
i = 0
errorflag = 0
errorflag2 = 0
errortemplist = []
while i < lense:
    proxy = config.proxyPool[(datetime.datetime.now().hour + dev) % len(config.proxyPool)]
    manga = mangaList[i]
    print(str(i + 1) + '/' + str(lense))
    if manga[3] == '':
        sqlstr = 'UPDATE manga SET autostate = 6 WHERE id = "%s"' % (manga[0])
        c.execute(sqlstr)
        conn.commit()
        i += 1
        continue
    url = manga[3]
    try:
        data = se.get(url, headers=config.header, cookies=config.cookies, proxies=proxy).text
        torrentExist = re.search("There are no torrents for this gallery", data)
        if torrentExist is not None:
            sqlstr = 'UPDATE manga SET autostate = 6 WHERE id = "%s"' % (manga[0])
            c.execute(sqlstr)
            conn.commit()
            i += 1
            continue
        if 'torrent' not in data:
            raise 'error'
    except:
        print('error', url, proxy)
        errorflag += 1
        dev += 1
        if errorflag >= 5:
            raise 'error'
        else:
            time.sleep(2)
            continue

    errorflag = 0
    seeds = 0
    size = ''
    torrentLink = ''
    re_torrent = """(?s)Posted:</span> <span>(.*?)</span></td>.*?Size:</span> (.*?)</td>.*?Seeds:</span> (\d+)</td>.*?Peers:</span> (\d+)</td>.*?Downloads:</span> (\d+)</td>.*?<a href=\"(.*?)\" onclick=\"document\.location='(.*?)'; return false\">"""
    torrentList = re.findall(re_torrent, data)
    for torrent in torrentList:
        if int(torrent[2]) > 0:
            torrentLink = torrent[5]
            size = torrent[1]
            seeds = int(torrent[2])
            break
    for torrent in torrentList:
        if int(torrent[2]) == 0:
            continue
        if int(torrent[2]) > seeds and size == torrent[1]:
            seeds = int(torrent[2])
            torrentLink = torrent[5]

    # print(torrentLink)

    if torrentLink == '':
        sqlstr = 'UPDATE manga SET autostate = 6 WHERE id = "%s"' % (manga[0])
        c.execute(sqlstr)
        conn.commit()

    else:
        time.sleep(1)
        try:
            response = requests.get(torrentLink, headers=config.header, cookies=config.cookies, proxies=proxy)
            if response.text == 'The torrent file could not be found. Most likely you have mistyped the URL, or the torrent is no longer available.':
                raise 'error'
        except:
            time.sleep(1)
            dev += 1
            print('error', torrentLink)
            proxy = config.proxyPool[(datetime.datetime.now().hour + dev) % len(config.proxyPool)]
            response = requests.get(torrentLink, headers=config.header, cookies=config.cookies, proxies=proxy)

        if response.text == 'The torrent file could not be found. Most likely you have mistyped the URL, or the torrent is no longer available.':
            errorflag2 += 1
            print('The torrent file could not be found')
            sqlstr = 'UPDATE manga SET autostate = 6 WHERE id = "%s"' % (manga[0])
            c.execute(sqlstr)
            conn.commit()
            errortemplist.append(manga)
            if errorflag2 >= 5:
                for mangatemp in errortemplist:
                    sqlstr = 'UPDATE manga SET autostate = 2 WHERE autostate = 6 AND id = "%s"' % (manga[0])
                    c.execute(sqlstr)
                conn.commit()
                raise 'download torrent error:The torrent file could not be found'

        else:
            errorflag2 = 0
            errortemplist = []

            print(torrentLink)
            idnum = manga[0].split('/')[0]
            qbt_client.torrents_add(torrent_files=response.content,
                                    save_path=config.qbit_torrent_path + idnum, category="autoehentai",
                                    rename=idnum)
            time.sleep(3)
            torrentinfo = ''
            torrents_qbit = qbt_client.torrents.info()
            for torrent in torrents_qbit:
                if torrent.name == idnum:
                    torrentinfo = torrent
                    break
            if torrentinfo == '':
                time.sleep(3)
                torrents_qbit = qbt_client.torrents.info()
                for torrent in torrents_qbit:
                    if torrent.name == idnum:
                        torrentinfo = torrent
                        break
            if torrentinfo == '':
                print('torrent add error', idnum)
                sqlstr = 'UPDATE manga SET autostate = -3 WHERE id = "%s"' % (manga[0])
                c.execute(sqlstr)
                conn.commit()
            else:
                filename = torrentinfo.content_path[len(torrentinfo.save_path) + 1:]
                print(filename)
                sqlstr = 'UPDATE manga SET autostate = 4 ,filename = "%s" ,torrenthash = "%s" WHERE id = "%s"' % (
                    filename, torrentinfo.hash, manga[0])
                c.execute(sqlstr)
                conn.commit()

    print(manga[0], manga[1])
    i += 1
    if i < lense:
        time.sleep(30 + random.randint(0, 60))

print('done')
