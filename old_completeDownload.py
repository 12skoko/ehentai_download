import qbittorrentapi
import os
import zipfile
import requests
import time
import paramiko
import re
from bs4 import BeautifulSoup
from TagTranslation import EhTagTranslation
import random
import config
import datetime
import html
from requests_toolbelt.multipart.encoder import MultipartEncoder
import shutil


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


def parseinfo(html):
    soup = BeautifulSoup(html, 'lxml')
    name = soup.find("h1", id="gj").text.replace('"', '""')
    romaname = soup.find("h1", id="gn").text.replace('"', '""')
    if name == '':
        name = romaname
        romaname = ''
    category = soup.find("div", id="gdc").text
    uploader = soup.find("div", id="gdn").text
    bs_td = soup.find_all("td", class_="gdt2")
    postedtime = bs_td[0].text
    parent = bs_td[1].text
    language = bs_td[3].text.replace("\xa0", "")
    estimatedsize = bs_td[4].text
    pages = int(bs_td[5].text.replace(" pages", ""))
    favorited = int(bs_td[6].text.replace(" times", "").replace("Once", "1").replace("Never", "0"))
    rating_count = int(soup.find("span", id="rating_count").text)
    rating = int(float(soup.find("td", id="rating_label").text.replace("Average: ", "")) * 100)
    tagstrings = soup.find("div", id="taglist")
    taglist = []
    for text in tagstrings.strings:
        if ':' in text:
            row = text
        else:
            taglist.append(row + text)
    tag = ','.join(taglist)
    # div=soup.find('div', id='gd5')
    # p_element = soup.find('p', class_='g2 gsp')
    onclick_value = soup.find('a', href="#", string='Archive Download').get('onclick')
    # print(a_element)
    # onclick_value = a_element
    downloadlink = re.search("return popUp\('(https:\/\/exhentai\.org\/archiver\.php.*?)',480,320\)", onclick_value)[1]
    return name, romaname, category, uploader, postedtime, language, estimatedsize, pages, favorited, rating_count, rating, tag, downloadlink, parent


def upload(manga, directorypath):
    print(manga[0], manga[1])
    sqlstr = 'SELECT * FROM mangainfo WHERE id="%s";' % (manga[0])
    c.execute(sqlstr)
    info = c.fetchall()[0]
    # print(info)
    filepath = os.path.join(directorypath, manga[15])
    filepath = os.path.normpath(filepath).replace('\\', '/')
    print(filepath)
    tempfilename = manga[15].replace('[' + manga[0].split('/')[0] + ']', '')
    tempfilename = '[' + manga[0].split('/')[0] + ']' + tempfilename
    tempfilepath = os.path.join(config.upload_temp_path, tempfilename)
    try:
        shutil.copy(filepath, tempfilepath)
        with open(tempfilepath, 'rb') as file_obj:
            encoder = MultipartEncoder(
                fields={'file': (tempfilename, file_obj, 'application/x-zip-compressed'), 'catid': ''})
            response = requests.post(config.raragi_url + '/upload', data=encoder, cookies=raragiCookie,
                                     headers={'Content-Type': encoder.content_type})

    except Exception as e:
        sqlstr = 'UPDATE manga SET state = -5 ,remark="%s|%s" WHERE id = "%s"' % (e, filepath, manga[0])
        c.execute(sqlstr)
        conn.commit()
        print('OSError', manga[0], manga[1])
        if os.path.exists(tempfilepath):
            os.remove(tempfilepath)
        return
    # file_size = os.path.getsize(filepath)
    time.sleep(1)
    # print(response.json())
    jobid = response.json()['job']
    joburl = config.raragi_url + f'/api/minion/{jobid}/detail'
    response = requests.get(joburl, cookies=raragiCookie).json()
    # print(response)
    flag = 0
    while response['finished'] is None:
        time.sleep(1)
        response = requests.get(joburl, cookies=raragiCookie).json()
        flag += 1
        if flag > 300:
            raise 'uploaderror'
    result = response['result']
    if result['success'] != 1:
        print(result['message'])
        sqlstr = 'UPDATE manga SET state = -5 ,remark="%s|%s" WHERE id = "%s"' % (filepath, result['message'], manga[0])
        c.execute(sqlstr)
        conn.commit()
        os.remove(tempfilepath)
        return
    else:
        id = result['id']

    os.remove(tempfilepath)

    date_added = int(time.time())
    tagstr = f'romaname:{info[2]},source:{info[5]},category:{info[6]},uploader:{info[7]},postedtime:{info[8]},language:{info[9]},pages:{info[11]},favorited:{info[12]},ratingcount:{info[13]},rating:{info[14]},updatetime:{info[15]},date_added:{date_added}'
    tagstr = tagstr + ',' + info[18] + ',' + info[17]

    data = {
        'title': info[1],
        'tags': tagstr}

    update_url = config.raragi_url + '/api/archives/%s/metadata' % id
    res2 = requests.put(update_url, headers=config.raragi_auth, data=data)
    # print(response.text)

    # print(data)
    sqlstr = 'UPDATE manga SET state = 0 WHERE id = "%s"' % (manga[0])
    c.execute(sqlstr)
    conn.commit()


def check_complete(base_directory, partial_directory_name, file_name="galleryinfo.txt"):
    for item in os.listdir(base_directory):
        item_path = os.path.join(base_directory, item)
        if os.path.isdir(item_path) and partial_directory_name in item:
            # 检查目录中是否存在指定的文件
            for file_item in os.listdir(item_path):
                if os.path.isfile(os.path.join(item_path, file_item)) and file_item == file_name:
                    return True, item
    return False, ""


def is_folder_all_files(folder_path):
    for item in os.listdir(folder_path):
        item_path = os.path.join(folder_path, item)
        if os.path.isdir(item_path):
            return False
    return True


def create_zip_file(folder_path, zip_file_name):
    with zipfile.ZipFile(zip_file_name, 'w', zipfile.ZIP_STORED) as zip_file:
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                file_path = os.path.join(root, file)
                zip_file.write(file_path, os.path.relpath(file_path, folder_path))


def get_folder_name(base_dir, partial_name):
    for dirpath, dirnames, filenames in os.walk(base_dir):
        for dirname in dirnames:
            if partial_name in dirname:
                return os.path.join(dirpath, dirname)
    return None


def completeTorrent():
    print('-------------------completeTorrent-------------------')
    torrents = qbt_client.torrents_info()
    for torrent in torrents:
        if torrent.category == 'ehentai':
            print(torrent.name)
            if torrent['completion_on'] > 0:
                if os.path.isdir(
                        os.path.join(config.torrent_download_path, torrent.content_path[len(config.qbit_torrent_path):])):
                    sqlstr = 'UPDATE manga SET state = 7,remark="isdir" WHERE state = 5 and torrenthash = "%s"' % (
                        torrent.hash)
                else:
                    sqlstr = 'UPDATE manga SET state = 7 WHERE state = 5 and torrenthash = "%s"' % (torrent.hash)
                # print(torrent.name)
                c.execute(sqlstr)
                conn.commit()
            if torrent['tags'] == 'fatel':
                sqlstr = 'UPDATE manga SET state = 6 , filename=NULL WHERE state = 5 and torrenthash = "%s"' % (
                    torrent.hash)
                print('fatel:', torrent.name)
                c.execute(sqlstr)
                conn.commit()


def completeHah():
    print('-------------------completeHah-------------------')
    sqlstr = 'SELECT * FROM manga WHERE state = 9;'
    c.execute(sqlstr)
    mangalist = c.fetchall()
    for manga in mangalist:
        print(manga[0], manga[1])
        partial_name = '[' + manga[0].split('/')[0] + ']'
        flag = check_complete(config.hah_download_path, partial_name)
        if flag[0] == True:
            sqlstr = f'UPDATE manga set state = 10, alias="{flag[1]}" WHERE state = 9 and id="{manga[0]}";'
            print(sqlstr)
            c.execute(sqlstr)
            conn.commit()


def compressTorrent():
    print('-------------------compressTorrent-------------------')
    sqlstr = 'SELECT * FROM manga WHERE state = 7 AND remark="isdir";'
    c.execute(sqlstr)
    res = c.fetchall()
    i = 1
    lense = str(len(res))
    for manga in res:
        path = os.path.join(config.torrent_download_path, manga[0].split('/')[0], manga[15])
        print(str(i) + '/' + lense + ':', manga[0], manga[1])
        zip_file_name = '[' + manga[0].split('/')[0] + ']' + re.sub(r'[\\/*?:"<>|]', '_', manga[15]) + '.zip'
        zip_file_path = os.path.join(config.torrent_zip_path, zip_file_name)
        try:
            create_zip_file(path, zip_file_path)
        except:
            print('compress error:', manga[0])
            sqlstr = f'UPDATE manga SET state=-4,remark="compress torrent error" WHERE id="{manga[0]}";'
            c.execute(sqlstr)
            conn.commit()
            i += 1
            continue
        sqlstr = f'UPDATE manga SET remark="compressed",filename="{zip_file_name}",alias="{manga[15]}" WHERE id="{manga[0]}";'
        c.execute(sqlstr)
        conn.commit()
        i += 1


def compressHah():
    print('-------------------compressHah-------------------')
    sqlstr = 'SELECT * FROM manga WHERE state = 10;'
    c.execute(sqlstr)
    res = c.fetchall()
    i = 1
    lense = str(len(res))
    for manga in res:
        partial_name = '[' + manga[0].split('/')[0] + ']'
        folder_name = get_folder_name(config.hah_download_path, partial_name)
        print(str(i) + '/' + lense + ':', manga[0], manga[1])
        idname = '[' + manga[0].split('/')[0] + ']'
        if idname in config.too_long_name_list:
            zip_file_name = config.too_long_name_list[idname]
        else:
            zip_file_name = idname + re.sub(r'[\\/*?:"<>|]', '_', manga[1]) + '.zip'
        zip_file_path = os.path.join(config.hah_zip_path, zip_file_name)
        try:
            create_zip_file(folder_name, zip_file_path)
        except Exception as e:
            print(zip_file_name)
            print('compress error:', manga[0], '\n', e)
            sqlstr = f'UPDATE manga SET state=-4,remark="compress hah error" WHERE id="{manga[0]}";'
            c.execute(sqlstr)
            conn.commit()
            i += 1
            continue
        sqlstr = f'UPDATE manga SET state = 12,filename="{zip_file_name}" WHERE id="{manga[0]}";'
        c.execute(sqlstr)
        conn.commit()
        i += 1


def collectTorrent():
    print('-------------------collectTorrent-------------------')
    se = requests.session()
    tagTrans = EhTagTranslation()
    sqlstr = 'SELECT * FROM manga WHERE state = 7 ORDER BY timestamp DESC;'
    c.execute(sqlstr)
    mangaList = c.fetchall()
    lense = len(mangaList)
    dev = 0
    i = 0
    errorflag = 0
    while i < lense:
        proxy = config.proxyPool[(datetime.datetime.now().hour + dev) % len(config.proxyPool)]
        manga = mangaList[i]
        print(str(i + 1) + '/' + str(lense))
        url = manga[2]
        try:
            data = se.get(url, headers=config.header, cookies=config.cookies, proxies=proxy).text
            info = parseinfo(data)
        except:
            print('error', url, proxy)
            # print(data)
            errorflag += 1
            dev += 1
            if errorflag >= 5:
                raise 'error'
            else:
                time.sleep(2)
                continue
        errorflag = 0
        id = manga[0]
        name = html.unescape(info[0]).replace('"', '""')
        realname = getRealname(name)
        filename = manga[15].replace('"', '""')
        updatetime = time.time()
        tag_tran = tagTrans.getTrans(info[11]).replace('"', '""')

        sqlstr = 'SELECT * FROM mangainfo WHERE id = "%s"' % (manga[0])
        c.execute(sqlstr)
        res = c.fetchall()
        if res:
            sqlstr = 'DELETE FROM mangainfo WHERE id = "%s"' % (manga[0])
            c.execute(sqlstr)
            print('updateinfo' + manga[0])

        sqlstr = 'INSERT INTO mangainfo (id,name,romaname,realname,filename,link,category,uploader,postedtime,language,estimatedsize,pages,favorited,ratingcount,rating,updatetime,state,tag,tagtran)values("%s","%s","%s","%s","%s","%s","%s","%s","%s","%s","%s",%d,%d,%d,%d,%d,%d,"%s","%s");' \
                 % (id, name, info[1], realname, filename, url, info[2], info[3], info[4], info[5], info[6], info[7],
                    info[8], info[9], info[10], updatetime, 1, info[11], tag_tran)
        print('insert mangainfo:', manga[0], manga[1])
        try:
            c.execute(sqlstr)
        except Exception as e:
            print('insert mangainfo error', manga[0], manga[1])
            print(e)
            print(sqlstr)
            raise 'insert mangainfo error'
        sqlstr = 'UPDATE manga SET state = 8 WHERE id = "%s"' % (manga[0])
        c.execute(sqlstr)
        conn.commit()

        i += 1
        if i < lense:
            time.sleep(10 + random.randint(10, 30))


def uploadall():
    print('-------------------uploadall-------------------')
    sqlstr = 'SELECT * FROM manga WHERE state = 8;'
    c.execute(sqlstr)
    mangaList = c.fetchall()
    length = str(len(mangaList))
    i = 1
    for manga in mangaList:
        print('torrent:' + str(i) + '/' + length)
        if manga[12] == 'compressed':
            upload(manga, config.torrent_zip_path)
        else:
            upload(manga, os.path.join(config.torrent_download_path, manga[0].split('/')[0]))
        i += 1
        time.sleep(2)

    sqlstr = 'SELECT * FROM manga WHERE state = 12;'
    c.execute(sqlstr)
    mangaList = c.fetchall()
    length = str(len(mangaList))
    i = 1
    for manga in mangaList:
        print('hah:' + str(i) + '/' + length)
        upload(manga, config.hah_zip_path)
        i += 1
        time.sleep(2)

    sqlstr = 'SELECT * FROM manga WHERE state = 11;'
    c.execute(sqlstr)
    mangaList = c.fetchall()
    length = str(len(mangaList))
    i = 1
    for manga in mangaList:
        print('direct:' + str(i) + '/' + length)
        upload(manga, config.direct_download_path)
        i += 1
        time.sleep(2)

    requests.post(config.raragi_url + '/api/regen_thumbs?force=0', cookies=raragiCookie)


def delete():
    print('-------------------delete-------------------')

    contents = os.listdir(config.torrent_download_path)
    i = 1
    length = str(len(contents))
    for item in contents:
        sqlstr = f'SELECT * FROM manga WHERE (state=0 OR state=6) AND id LIKE "{item}/%";'
        c.execute(sqlstr)
        res = c.fetchall()
        if res:
            file_path = os.path.join(config.torrent_delete_path, item)
            shutil.rmtree(file_path, ignore_errors=True)
            time.sleep(0.2)
            print('deleted ' + str(i) + '/' + length + ':' + file_path)
            # remote_file_path = os.path.join(config.torrent_delete_path, item)
            # stdin, stdout, stderr = ssh.exec_command(f"rm -r {remote_file_path}")
            # time.sleep(0.2)
            # print('deleted ' + str(i) + '/' + length + ':' + remote_file_path)
        i += 1

    contents = os.listdir(config.torrent_zip_path)
    i = 1
    length = str(len(contents))
    for item in contents:
        id = re.search('\[(\d+)\].+', item)[1]
        sqlstr = f'SELECT * FROM manga WHERE state=0 AND id LIKE "{id}%";'
        c.execute(sqlstr)
        res = c.fetchall()
        if res:
            # print(item)
            file_path = os.path.join(config.torrent_zip_delete_path, item)
            os.remove(file_path)
            time.sleep(0.2)
            print('deleted ' + str(i) + '/' + length + ':' + file_path)
        i += 1

    contents = os.listdir(config.hah_download_path)
    i = 1
    length = str(len(contents))
    for item in contents:
        id = re.search('.+\[(\d+)\]', item)[1]
        sqlstr = f'SELECT * FROM manga WHERE state=0 AND id LIKE "{id}%";'
        c.execute(sqlstr)
        res = c.fetchall()
        if res:
            file_path = os.path.join(config.hah_download_path, item)
            shutil.rmtree(file_path, ignore_errors=True)
            time.sleep(0.2)
            print('deleted ' + str(i) + '/' + length + ':' + file_path)
            # remote_file_path = os.path.join(config.delhahpath, "'" + item + "'")
            # stdin, stdout, stderr = ssh.exec_command(f"rm -r {remote_file_path}")
            # time.sleep(0.2)
            # print('deleted ' + str(i) + '/' + length + ':' + remote_file_path)
        i += 1

    contents = os.listdir(config.hah_zip_path)
    i = 1
    length = str(len(contents))
    for item in contents:
        id = re.search('\[(\d+)\].+', item)[1]
        sqlstr = f'SELECT * FROM manga WHERE state=0 AND id LIKE "{id}%";'
        c.execute(sqlstr)
        res = c.fetchall()
        if res:
            # print(item)
            file_path = os.path.join(config.hah_zip_delete_path, item)
            os.remove(file_path)
            time.sleep(0.2)
            print('deleted ' + str(i) + '/' + length + ':' + file_path)
        i += 1

    contents = os.listdir(config.direct_download_path)
    i = 1
    length = str(len(contents))
    for item in contents:
        id = re.search('\[(\d+)\].+', item)[1]
        sqlstr = f'SELECT * FROM manga WHERE state=0 AND id LIKE "{id}%";'
        c.execute(sqlstr)
        res = c.fetchall()
        if res:
            # print(item)
            file_path = os.path.join(config.direct_delete_path, item)
            os.remove(file_path)
            time.sleep(0.2)
            print('deleted ' + str(i) + '/' + length + ':' + file_path)
        i += 1

    i = 1
    torrents = qbt_client.torrents_info()
    length = str(len(torrents))
    for torrent in torrents:
        if torrent.category == 'ehentai':
            if 'fatel' in torrent.tags:
                qbt_client.torrents_delete(delete_files=True, torrent_hashes=torrent.hash)
                time.sleep(0.2)
                print('deleted_fatel_torrent:' + str(i) + '/' + length + ':' + torrent.name)
                i += 1
                continue
            sqlstr = f'SELECT * FROM manga WHERE state=0 AND torrenthash="{torrent.hash}";'
            c.execute(sqlstr)
            res = c.fetchall()
            if res:
                qbt_client.torrents_delete(torrent_hashes=torrent.hash)
                time.sleep(0.2)
                print('deleted_torrent:' + str(i) + '/' + length + ':' + torrent.name)
            i += 1


req = requests.post(url=config.raragi_url + "/login", data={'password': config.raragi_password})
cook = req.headers['Set-Cookie'].split("=")
raragiCookie = {cook[0]: cook[1]}

conn = config.conn
c = conn.cursor()

qbt_client = qbittorrentapi.Client(**config.qbit_login)
qbt_client.auth_log_in()

# ssh = paramiko.SSHClient()
# ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
# ssh.connect(**config.ssh_login)

while 1:
    completeTorrent()
    completeHah()
    compressTorrent()
    compressHah()
    collectTorrent()
    uploadall()
    delete()
    print('done')
    time.sleep(3600)
